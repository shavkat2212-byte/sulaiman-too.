import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime
import io

DB_FILE = "sklad_data.json"

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("products", {})
                data.setdefault("sales", [])
                data.setdefault("cash_operations", [])
                data.setdefault("supplier_payments", [])
                if data.get("products") and not isinstance(next(iter(data["products"].values()), []), list):
                    data["products"] = {}
                return data
        except:
            pass
    return {"products": {}, "sales": [], "cash_operations": [], "supplier_payments": []}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет")

# ==================== БОКОВАЯ ПАНЕЛЬ ====================
menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление", 
    "💰 Касса / Продажи", 
    "💵 Баланс Кассы",
    "📊 Отчеты по дням",
    "🧾 Оплата контрагентам"
])

st.sidebar.markdown("---")
st.sidebar.subheader("Настройки системы")
if st.sidebar.button("⚠️ Перезагрузить базу (Очистить)", type="secondary"):
    data = {"products": {}, "sales": [], "cash_operations": [], "supplier_payments": []}
    st.session_state.data = data
    save_data(data)
    st.sidebar.success("База данных успешно очищена!")
    st.rerun()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_flat_stock():
    flat = []
    total_qty = total_cost = total_retail = 0.0
    for p_name, batches in data["products"].items():
        if isinstance(batches, list):
            for b in batches:
                if b.get("qty", 0) > 0:
                    qty = b["qty"]
                    cost = b.get("cost", 0)
                    price = b.get("price", 0)
                    flat.append({
                        "Товар": p_name.capitalize(),
                        "Дата поступления": b["date"],
                        "В наличии (шт)": qty,
                        "Закупка (сом)": cost,
                        "Продажа (сом)": price,
                        "Себестоимость партии (сом)": round(qty * cost, 2)
                    })
                    total_qty += qty
                    total_cost += qty * cost
                    total_retail += qty * price
    return pd.DataFrame(flat), total_qty, total_cost, total_retail

def save_product_smart(name, qty, cost, price, date_str):
    name = name.strip().lower()
    if not name:
        return False
    if name not in data["products"]:
        data["products"][name] = []
    for batch in data["products"][name]:
        if batch["date"] == date_str:
            batch["qty"] = qty
            batch["cost"] = cost
            batch["price"] = price
            return True
    data["products"][name].append({
        "date": date_str, "qty": qty, "cost": cost, "price": price
    })
    return True

# ==================== ВКЛАДКА 1: СКЛАД ====================
if menu == "📦 Склад / Поступление":
    st.header("Управление складом")

    df_stock, total_qty, total_cost, total_retail = get_flat_stock()

    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Всего товаров в наличии", f"{int(total_qty)} шт.")
    c2.metric("💰 Сумма склада в закупке", f"{total_cost:,.2f} сом")
    c3.metric("📈 Розничная стоимость склада", f"{total_retail:,.2f} сом")

    print_mode = st.checkbox("🖨️ Режим для печати отчёта")

    if print_mode:
        st.subheader("📄 ОТЧЁТ ПО ОСТАТКАМ ТОВАРОВ НА СКЛАДЕ")
        st.write(f"Дата формирования: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if not df_stock.empty:
            df_print = df_stock.copy()
            df_print["Закупка (сом)"] = df_print["Закупка (сом)"].map('{:,.2f} сом'.format)
            df_print["Продажа (сом)"] = df_print["Продажа (сом)"].map('{:,.2f} сом'.format)
            df_print["Себестоимость партии (сом)"] = df_print["Себестоимость партии (сом)"].map('{:,.2f} сом'.format)
            st.table(df_print)
            st.markdown(f"**Итого на складе:** {int(total_qty)} шт. на общую сумму закупки **{total_cost:,.2f} сом**")
        else:
            st.info("Склад пуст")
    else:
        st.subheader("📥 Загрузка/Обновление товаров из Excel (.xlsx или .csv)")
        uploaded = st.file_uploader("Выберите файл таблицы", type=["csv", "xlsx"])
        if uploaded:
            try:
                if uploaded.name.endswith(".xlsx"):
                    df = pd.read_excel(uploaded)
                else:
                    try:
                        df = pd.read_csv(uploaded, encoding="utf-8")
                    except:
                        uploaded.seek(0)
                        df = pd.read_csv(uploaded, sep=None, engine="python", encoding="cp1251")

                imported = 0
                today = datetime.now().strftime("%Y-%m-%d")
                for _, row in df.iterrows():
                    try:
                        name = str(row.iloc[0]).strip()
                        if not name or name.lower() == "nan": continue
                        qty = int(float(str(row.iloc[1]).replace(" ", "").replace(",", ".")))
                        cost = float(str(row.iloc[2]).replace(" ", "").replace(",", "."))
                        price = float(str(row.iloc[3]).replace(" ", "").replace(",", "."))
                        if save_product_smart(name, qty, cost, price, today):
                            imported += 1
                    except: continue
                if imported > 0:
                    save_data(data)
                    st.success(f"🚀 Склад успешно синхронизирован! Обработано товаров: {imported}")
                    st.rerun()
            except Exception as e:
                st.error(f"Не удалось прочитать файл: {e}")

        st.markdown("---")

        col_add, col_edit = st.columns(2)
        with col_add:
            st.subheader("➕ Добавить товар вручную")
            with st.form("add_form", clear_on_submit=True):
                name = st.text_input("Название товара").strip().lower()
                qty = st.number_input("Количество", min_value=1, value=1)
                cost = st.number_input("Закупка (сом)", min_value=0.0, step=10.0)
                price = st.number_input("Цена продажи, сом", min_value=0.0, step=10.0)
                if st.form_submit_button("Сохранить в БД"):
                    if name:
                        today = datetime.now().strftime("%Y-%m-%d")
                        save_product_smart(name, qty, cost, price, today)
                        save_data(data)
                        st.success("Успешно сохранено!")
                        st.rerun()

        with col_edit:
            st.subheader("✏️ Редактировать / Удалить партию")
            if not data["products"]:
                st.write("На складе еще нет товаров.")
            else:
                options = {}
                for p_name, batches in data["products"].items():
                    if isinstance(batches, list):
                        for idx, b in enumerate(batches):
                            if b.get("qty", 0) > 0:
                                label = f"{p_name.capitalize()} (Приход: {b['date']}) — Остаток: {b['qty']} шт."
                                options[label] = (p_name, idx)
                
                if options:
                    selected = st.selectbox("Выберите запись для изменения", list(options.keys()))
                    p_key, b_idx = options[selected]
                    current = data["products"][p_key][b_idx]
                    
                    with st.form("edit_form"):
                        new_qty = st.number_input("Изменить остаток (шт)", min_value=0, value=int(current["qty"]))
                        new_cost = st.number_input("Цена закупки", min_value=0.0, value=float(current["cost"]))
                        new_price = st.number_input("Цена продажи", min_value=0.0, value=float(current["price"]))
                        
                        c_btn1, c_btn2 = st.columns(2)
                        save_changes = c_btn1.form_submit_button("💾 Сохранить изменения")
                        delete_batch_click = c_btn2.form_submit_button("🗑️ Удалить", type="secondary")
                        
                        if save_changes:
                            data["products"][p_key][b_idx] = {
                                "date": current["date"], "qty": new_qty, "cost": new_cost, "price": new_price
                            }
                            save_data(data)
                            st.success("Данные успешно изменены!")
                            st.rerun()
                        
                        if delete_batch_click:
                            st.session_state.show_batch_delete = {"key": p_key, "index": b_idx, "label": selected}

                    if "show_batch_delete" in st.session_state and st.session_state.show_batch_delete:
                        b_del = st.session_state.show_batch_delete
                        @st.dialog("⚠️ Подтверждение удаления")
                        def delete_batch_dialog():
                            st.error(f"Удалить выбранную партию?\n{b_del['label']}")
                            col_y, col_n = st.columns(2)
                            if col_y.button("🗑️ Да, удалить", type="primary", use_container_width=True):
                                data["products"][b_del['key']].pop(b_del['index'])
                                if not data["products"][b_del['key']]:
                                    del data["products"][b_del['key']]
                                save_data(data)
                                st.session_state.show_batch_delete = None
                                st.success("Удалено!")
                                st.rerun()
                            if col_n.button("Отмена", type="secondary", use_container_width=True):
                                st.session_state.show_batch_delete = None
                                st.rerun()
                        delete_batch_dialog()

        st.markdown("---")
        st.subheader("📋 Список всех товаров на складе")
        if not df_stock.empty:
            df_display = df_stock.copy()
            df_display["Закупка (сом)"] = df_display["Закупка (сом)"].map('{:,.2f} сом'.format)
            df_display["Продажа (сом)"] = df_display["Продажа (сом)"].map('{:,.2f} сом'.format)
            df_display["Себестоимость партии (сом)"] = df_display["Себестоимость партии (сом)"].map('{:,.2f} сом'.format)
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.write("Склад пуст.")

# ==================== ВКЛАДКА 2: КАССА / ПРОДАЖИ ====================
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу")
    if not data["products"]:
        st.warning("Сначала добавьте товары на склад.")
    else:
        available = [p.capitalize() for p, batches in data["products"].items() 
                     if isinstance(batches, list) and any(b.get("qty", 0) > 0 for b in batches)]
                     
        if not available:
            st.error("Нет товаров в наличии!")
        else:
            sel_display = st.selectbox("🔍 Выберите товар для продажи", sorted(available))
            p_key = sel_display.lower()
            
            batches_options = {}
            for b_idx, b in enumerate(data["products"][p_key]):
                if b["qty"] > 0:
                    label = f"Поступление от {b['date']} (Остаток: {b['qty']} шт., Цена: {b['price']} сом)"
                    batches_options[label] = b_idx
                    
            selected_batch_label = st.selectbox("📦 С какой даты поступления списать товар?", list(batches_options.keys()))
            b_index = batches_options[selected_batch_label]
            chosen_batch = data["products"][p_key][b_index]
            
            sqty = st.number_input("Количество для продажи (шт)", min_value=1, max_value=int(chosen_batch["qty"]), value=1)
            custom_price = st.number_input("💰 Цена продажи за 1 шт (можно изменить), сом", min_value=0.0, value=float(chosen_batch['price']))
            pay_method = st.radio("💳 Способ оплаты", ["Наличные", "Рассрочка"], horizontal=True)
            
            # ИСПРАВЛЕНО: Добавлено поле первоначального взноса, если выбрана Рассрочка
            down_payment = 0.0
            total_sale_sum = sqty * custom_price
            
            if pay_method == "Рассрочка":
                down_payment = st.number_input("💵 Первоначальный взнос (в кассу наличными), сом", min_value=0.0, max_value=float(total_sale_sum), value=0.0, step=100.0)
            
            credit_balance = total_sale_sum - down_payment

            if st.button("💵 Оформить продажу", type="primary"):
                st.session_state.show_confirmation = {
                    "p_key": p_key, "b_index": b_index, "name": sel_display, "batch_date": chosen_batch["date"],
                    "qty": sqty, "price": custom_price, "total": total_sale_sum, "payment": pay_method,
                    "down_payment": down_payment, "credit_balance": credit_balance
                }

            if "show_confirmation" in st.session_state and st.session_state.show_confirmation:
                conf = st.session_state.show_confirmation
                
                @st.dialog("📋 Подтверждение операции")
                def confirm_dialog():
                    st.warning("Внимательно проверьте данные перед продажей:")
                    st.markdown(f"**Товар:** {conf['name']} (Поступление: {conf['batch_date']})")
                    st.markdown(f"**Количество:** {conf['qty']} шт. | **Цена за шт:** {conf['price']:.2f} сом")
                    st.markdown(f"### Общая сумма сделки: {conf['total']:.2f} сом")
                    
                    # ИСПРАВЛЕНО: Динамическое окно с расчетом взноса и остатка рассрочки
                    if conf['payment'] == "Рассрочка":
                        st.markdown(f"**Способ оплаты:** 📝 Рассрочка")
                        st.markdown(f"👉 **Вносится наличными сейчас:** {conf['down_payment']:.2f} сом")
                        st.markdown(f"👉 **Остаток долга в рассрочку:** {conf['credit_balance']:.2f} сом")
                    else:
                        st.markdown(f"**Способ оплаты:** 💵 Полные Наличные")
                    
                    st.write("")
                    col_yes, col_no = st.columns(2)
                    if col_yes.button("✅ Да, подтверждаю продажу", type="primary", use_container_width=True):
                        data["products"][conf['p_key']][conf['b_index']]["qty"] -= conf['qty']
                        t_cost = conf['qty'] * data["products"][conf['p_key']][conf['b_index']]["cost"]
                        
                        sale_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
                        
                        data["sales"].append({
                            "id": sale_id,
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "day": datetime.now().strftime("%Y-%m-%d"),
                            "name": f"{conf['name']} (Приход {conf['batch_date']})", 
                            "pure_name": conf['p_key'],
                            "batch_date": conf['batch_date'],
                            "qty": conf['qty'],
                            "total_sale": conf['total'], 
                            "total_cost": t_cost, 
                            "profit": conf['total'] - t_cost, 
                            "payment": conf['payment'],
                            "down_payment": conf['down_payment'],   # Сохраняем взнос
                            "credit_balance": conf['credit_balance'] # Сохраняем долг
                        })
                        save_data(data)
                        st.session_state.show_confirmation = None
                        st.success("🎉 Продажа успешно проведена!")
                        st.rerun()
                    if col_no.button("❌ Отмена", type="secondary", use_container_width=True):
                        st.session_state.show_confirmation = None
                        st.rerun()
                confirm_dialog()

# ==================== ВКЛАДКА 3: БАЛАНС КАССЫ ====================
elif menu == "💵 Баланс Кассы":
    st.header("💵 Состояние кассы магазина")
    
    # ИСПРАВЛЕНО: Наличные с продаж теперь считают ПОЛНЫЙ НАЛ + ПЕРВОНАЧАЛЬНЫЕ ВЗНОСЫ из рассрочек
    full_cash_sales = sum(s["total_sale"] for s in data["sales"] if s.get("payment") == "Наличные")
    down_payments_cash = sum(s.get("down_payment", 0.0) for s in data["sales"] if s.get("payment") == "Рассрочка")
    
    # Чистый остаток рассрочки (то, что нам должны)
    credit_debts = sum(s.get("credit_balance", s["total_sale"] if s.get("payment") == "Рассрочка" else 0.0) for s in data["sales"])
    
    manual_cash_flow = sum(op['amount'] for op in data.get('cash_operations', []))
    current_cash_in_hand = full_cash_sales + down_payments_cash + manual_cash_flow
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе (включая взносы)", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Чистый долг в рассрочке", f"{credit_debts:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль магазина", f"{sum(s['profit'] for s in data['sales']):,.2f} сом")
    
    st.markdown("---")
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
        op_amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
        op_comment = st.text_input("Комментарий / Причина")
        
        if st.form_submit_button("Выполнить операцию"):
            actual_amount = -op_amount if "Взять" in op_type else op_amount
            if 'cash_operations' not in data:
                data['cash_operations'] = []
            data['cash_operations'].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "amount": actual_amount,
                "comment": op_comment if op_comment else op_type
            })
            save_data(data)
            st.success("Операция по кассе успешно записана!")
            st.rerun()
            
    st.markdown("---")
    st.subheader("📜 История движений по кассе (ручные операции)")
    if not data.get('cash_operations', []):
        st.write("Ручных движений денег не было.")
    else:
        op_list = []
        for op in data['cash_operations'][::-1]:
            op_list.append({
                "Дата/Время": op['date'],
                "Изменение баланса": f"{op['amount']:+,.2f} сом",
                "Комментарий": op['comment']
            })
        st.dataframe(pd.DataFrame(op_list), use_container_width=True)

# ==================== ВКЛАДКА 4: ОТЧЕТЫ ====================
elif menu == "📊 Отчеты по дням":
    st.header("Аналитика и история продаж")
    if not data["sales"]:
        st.write("Продаж еще не было.")
    else:
        df = pd.DataFrame(data["sales"])
        df['day'] = pd.to_datetime(df['day']).dt.date
        
        st.subheader("🔍 Выберите период для просмотра отчета")
        date_range = st.date_input("Диапазон дат", value=(df['day'].min(), df['day'].max()))
        
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[(df['day'] >= start_date) & (df['day'] <= end_date)]
        else:
            filtered_df = df
            
        if filtered_df.empty:
            st.info("За выбранный период продаж не найдено.")
        else:
            c1, c2 = st.columns(2)
            c1.metric("💰 Общая Выручка за период", f"{filtered_df['total_sale'].sum():,.2f} сом")
            c2.metric("📈 Общая Чистая прибыль", f"{filtered_df['profit'].sum():,.2f} сом")
            
            if st.button("📥 Скачать этот отчет в Excel"):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    filtered_df.to_excel(writer, index=False, sheet_name="Продажи")
                st.download_button("Нажмите здесь для загрузки файла", data=output.getvalue(), 
                                   file_name=f"report_{datetime.now().strftime('%Y%m%d')}.xlsx")

            st.markdown("---")
            st.subheader("📋 Детализация продаж по типам оплаты")
            tab1, tab2, tab3 = st.tabs(["Все продажи", "💵 Наличные", "📝 Рассрочка"])
            
            # ИСПРАВЛЕНО: Функция рендеринга адаптирована под показ первоначального взноса и долга
            def render_sales_table_with_actions(dataframe, tab_name):
                if dataframe.empty:
                    st.write("Нет операций за этот период.")
                    return
                
                # Заголовки для таблиц
                if tab_name == "credit":
                    h1, h2, h3, h4, h5, h6, h7 = st.columns([1.5, 2, 0.8, 1.2, 1.2, 1.2, 1])
                    h1.markdown("**Дата/Время**")
                    h2.markdown("**Товар**")
                    h3.markdown("**Кол-во**")
                    h4.markdown("**Итого цена**")
                    h5.markdown("**Перв. взнос**")
                    h6.markdown("**Остаток долга**")
                    h7.markdown("**Действие**")
                else:
                    h1, h2, h3, h4, h5, h6 = st.columns([2, 2.5, 0.8, 1.5, 1.2, 1])
                    h1.markdown("**Дата/Время**")
                    h2.markdown("**Товар (Партия)**")
                    h3.markdown("**Кол-во**")
                    h4.markdown("**Сумма**")
                    h5.markdown("**Тип оплаты**")
                    h6.markdown("**Действие**")
                st.markdown("---")
                
                for idx, row in dataframe.iloc[::-1].iterrows():
                    if tab_name == "credit":
                        r1, r2, r3, r4, r5, r6, r7 = st.columns([1.5, 2, 0.8, 1.2, 1.2, 1.2, 1])
                        r1.write(row['date'])
                        r2.write(str(row['name']))
                        r3.write(f"{row['qty']} шт.")
                        r4.write(f"{row['total_sale']:.2f} c.")
                        r5.write(f"{row.get('down_payment', 0.0):.2f} c.")
                        r6.write(f"{row.get('credit_balance', row['total_sale']):.2f} c.")
                        action_col = r7
                    else:
                        r1, r2, r3, r4, r5, r6 = st.columns([2, 2.5, 0.8, 1.5, 1.2, 1])
                        r1.write(row['date'])
                        r2.write(str(row['name']))
                        r3.write(f"{row['qty']} шт.")
                        r4.write(f"{row['total_sale']:.2f} c.")
                        r5.write(row.get('payment', 'Наличные'))
                        action_col = r6
                    
                    button_key = f"del_{tab_name}_{row.get('id', idx)}"
                    if action_col.button("❌ Отменить", key=button_key, type="secondary"):
                        st.session_state.show_sale_delete = {
                            "index_in_data_sales": idx, 
                            "sale_id": row.get("id"),
                            "name": row['name'], 
                            "qty": row['qty'], 
                            "total": row['total_sale']
                        }
                        st.rerun()

            if "show_sale_delete" in st.session_state and st.session_state.show_sale_delete:
                s_del = st.session_state.show_sale_delete
                
                @st.dialog("⚠️ Отмена и удаление продажи")
                def delete_sale_dialog():
                    st.error("Вы уверены, что хотите ОТМЕНИТЬ эту продажу?")
                    st.markdown(f"**Операция:** {s_del['name']} | Количество: {s_del['qty']} шт.")
                    
                    col_y, col_n = st.columns(2)
                    if col_y.button("🔥 Да, отменить", type="primary", use_container_width=True):
                        target_idx = None
                        for i, s in enumerate(data["sales"]):
                            if s.get("id") == s_del["sale_id"]:
                                target_idx = i
                                break
                        
                        if target_idx is not None:
                            sale_item = data["sales"][target_idx]
                            p_pure = sale_item.get("pure_name", None)
                            b_date = sale_item.get("batch_date", None)
                            
                            if p_pure and b_date and p_pure in data["products"]:
                                batch_found = False
                                for b in data["products"][p_pure]:
                                    if b["date"] == b_date:
                                        b["qty"] += sale_item["qty"]
                                        batch_found = True
                                        break
                                if not batch_found:
                                    single_cost = sale_item["total_cost"] / sale_item["qty"]
                                    single_price = sale_item["total_sale"] / sale_item["qty"]
                                    data["products"][p_pure].append({"date": b_date, "qty": sale_item["qty"], "cost": single_cost, "price": single_price})
                            
                            data["sales"].pop(target_idx)
                            save_data(data)
                        
                        st.session_state.show_sale_delete = None
                        st.success("Продажа успешно отменена!")
                        st.rerun()
                        
                    if col_n.button("Назад", type="secondary", use_container_width=True):
                        st.session_state.show_sale_delete = None
                        st.rerun()
                delete_sale_dialog()

            with tab1:
                render_sales_table_with_actions(filtered_df, "all")
            with tab2:
                render_sales_table_with_actions(filtered_df[filtered_df['payment'] == 'Наличные'], "cash")
            with tab3:
                render_sales_table_with_actions(filtered_df[filtered_df['payment'] == 'Рассрочка'], "credit")

# ==================== ВКЛАДКА 5: ОПЛАТА КОНТРАГЕНТАМ ====================
elif menu == "🧾 Оплата контрагентам":
    st.header("Выплаты поставщикам и контрагентам")
    st.subheader("📤 Зафиксировать выплату")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента / поставщика")
        amount = st.number_input("Сумма выплаты (сом)", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий / Назначение платежа")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                data["supplier_payments"].append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "supplier": supplier.strip(),
                    "amount": amount,
                    "comment": comment
                })
                save_data(data)
                st.success("Выплата зафиксирована!")
                st.rerun()

    st.markdown("---")
    st.subheader("📜 История выплат контрагентам")
    if not data.get("supplier_payments"):
        st.info("Выплат ещё не было")
    else:
        df_pay = pd.DataFrame(data["supplier_payments"][::-1])
        df_display_pay = df_pay.copy()
        df_display_pay["amount"] = df_display_pay["amount"].map('{:,.2f} сом'.format)
        st.dataframe(df_display_pay, use_container_width=True, hide_index=True)
        
        total_paid = sum(p["amount"] for p in data["supplier_payments"])
        st.metric("Всего выплачено контрагентам", f"{total_paid:,.2f} сом")
