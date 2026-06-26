import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# Файл базы данных
DB_FILE = "sklad_data.json"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                loaded = json.load(f)
                if "products" in loaded and loaded["products"]:
                    first_item = next(iter(loaded["products"].values()))
                    if not isinstance(first_item, list):
                        return {"products": {}, "sales": [], "cash_operations": []}
                if "cash_operations" not in loaded:
                    loaded["cash_operations"] = []
                return loaded
            except:
                return {"products": {}, "sales": [], "cash_operations": []}
    return {"products": {}, "sales": [], "cash_operations": []}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет")

menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление", 
    "💰 Касса / Продажи", 
    "💵 Баланс Кассы",
    "📊 Отчеты по дням"
])

st.sidebar.markdown("---")
st.sidebar.subheader("Настройки системы")
if st.sidebar.button("⚠️ Перезагрузить базу (Очистить)", type="secondary"):
    data = {"products": {}, "sales": [], "cash_operations": []}
    st.session_state.data = data
    save_data(data)
    st.sidebar.success("База данных успешно очищена!")
    st.rerun()

def save_product_smart(name, qty, cost, price, date_str):
    if name not in data["products"]:
        data["products"][name] = []
    
    found = False
    for batch in data["products"][name]:
        if batch["date"] == date_str:
            batch["qty"] = qty
            batch["cost"] = cost
            batch["price"] = price
            found = True
            break
            
    if not found:
        data["products"][name].append({
            "date": date_str,
            "qty": qty,
            "cost": cost,
            "price": price
        })

# --- ВКЛАДКА 1: СКЛАД ---
if menu == "📦 Склад / Поступление":
    st.header("Управление товарами")
    
    total_qty = 0
    total_cost_sum = 0.0
    total_price_sum = 0.0
    
    for name, batches in data["products"].items():
        if isinstance(batches, list):
            for b in batches:
                if b["qty"] > 0:
                    total_qty += b["qty"]
                    total_cost_sum += b["qty"] * b["cost"]
                    total_price_sum += b["qty"] * b["price"]
                
    st.subheader("📊 Общие итоги по складу")
    if total_qty > 0:
        m1, m2, m3 = st.columns(3)
        m1.metric("📦 Всего товаров на складе", f"{total_qty} шт.")
        m2.metric("💰 Общая сумма в закупке", f"{total_cost_sum:,.2f} сом")
        m3.metric("📈 Потенциальная выручка", f"{total_price_sum:,.2f} сом")
    else:
        st.info("Склад пуст, показатели появятся после добавления товаров.")
        
    st.markdown("---")

    st.subheader("📥 Загрузка/Обновление товаров из Excel (.xlsx или .csv)")
    uploaded_file = st.file_uploader("Выберите файл таблицы", type=["csv", "xlsx"])
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                try:
                    df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='cp1251')
                except:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8')
            
            if df.shape[1] >= 4:
                imported_count = 0
                today_str = datetime.now().strftime("%Y-%m-%d")
                for index, row in df.iterrows():
                    try:
                        p_name = str(row.iloc[0]).strip().lower()
                        if not p_name or p_name == 'nan': continue
                            
                        p_qty = int(float(str(row.iloc[1]).strip().replace(' ', '').replace(',', '.')))
                        p_cost = float(str(row.iloc[2]).strip().replace(' ', '').replace(',', '.'))
                        p_price = float(str(row.iloc[3]).strip().replace(' ', '').replace(',', '.'))
                        
                        save_product_smart(p_name, p_qty, p_cost, p_price, today_str)
                        imported_count += 1
                    except: continue
                
                if imported_count > 0:
                    save_data(data)
                    st.success(f"🚀 Склад успешно синхронизирован! Обработано товаров: {imported_count}")
                    st.rerun()
        except Exception as e:
            st.error(f"Не удалось прочитать файл: {e}")

    st.markdown("---")
    
    col_add, col_edit = st.columns(2)
    with col_add:
        st.subheader("➕ Добавить товар вручную")
        with st.form("add_form", clear_on_submit=True):
            name = st.text_input("Название товара").strip().lower()
            qty = st.number_input("Количество (шт)", min_value=1, value=1)
            cost = st.number_input("Закупка (себестоимость), сом", min_value=0.0)
            price = st.number_input("Цена продажи, сом", min_value=0.0)
            
            if st.form_submit_button("Сохранить в БД"):
                if name:
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    save_product_smart(name, qty, cost, price, today_str)
                    save_data(data)
                    st.success("Успешно сохранено!")
                    st.rerun()

    with col_edit:
        st.subheader("✏️ Редактировать / Удалить партию")
        if not data["products"]:
            st.write("На складе еще нет товаров.")
        else:
            all_batches_options = {}
            for p_name, batches in data["products"].items():
                if isinstance(batches, list):
                    for b_idx, b in enumerate(batches):
                        if b["qty"] > 0:
                            display_label = f"{p_name.capitalize()} (Приход: {b['date']}) — Остаток: {b['qty']} шт."
                            all_batches_options[display_label] = (p_name, b_idx)
            
            if not all_batches_options:
                st.write("Нет активных товаров для изменения.")
            else:
                selected_batch_label = st.selectbox("Выберите запись для изменения", list(all_batches_options.keys()))
                p_key, b_index = all_batches_options[selected_batch_label]
                current_batch = data["products"][p_key][b_index]
                
                with st.form("edit_form"):
                    new_qty = st.number_input("Изменить остаток (шт)", min_value=0, value=int(current_batch["qty"]))
                    new_cost = st.number_input("Цена закупки, сом", min_value=0.0, value=float(current_batch["cost"]))
                    new_price = st.number_input("Цена продажи, сом", min_value=0.0, value=float(current_batch["price"]))
                    
                    c_btn1, c_btn2 = st.columns(2)
                    save_changes = c_btn1.form_submit_button("💾 Сохранить изменения")
                    delete_batch_click = c_btn2.form_submit_button("🗑️ Удалить", type="secondary")
                    
                    if save_changes:
                        data["products"][p_key][b_index] = {
                            "date": current_batch["date"], "qty": new_qty, "cost": new_cost, "price": new_price
                        }
                        save_data(data)
                        st.success("Данные успешно изменены!")
                        st.rerun()
                    
                    if delete_batch_click:
                        st.session_state.show_batch_delete = {"key": p_key, "index": b_index, "label": selected_batch_label}

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
    st.subheader("📋 Текущий остаток на складе")
    
    flat_stock_table = []
    for p_name, batches in data["products"].items():
        if isinstance(batches, list):
            for b in batches:
                if b["qty"] > 0:
                    flat_stock_table.append({
                        "Товар": p_name.capitalize(),
                        "Дата поступления": b["date"],
                        "В наличии (шт)": b["qty"],
                        "Закупка (1 шт)": f"{b['cost']:,} сом",
                        "Продажа (1 шт)": f"{b['price']:,} сом",
                        "Итого стоимость закупки": f"{b['qty'] * b['cost']:,} сом"
                    })
                
    if flat_stock_table:
        df_display = pd.DataFrame(flat_stock_table).sort_values(by=["Товар", "Дата поступления"])
        st.dataframe(df_display, use_container_width=True)
    else:
        st.write("Склад пуст.")

# --- ВКЛАДКА 2: КАССА (ПРОДАЖИ) ---
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу")
    if not data["products"]:
        st.warning("Сначала добавьте товары на склад.")
    else:
        available_product_names = []
        for p_name, batches in data["products"].items():
            if isinstance(batches, list) and any(b["qty"] > 0 for b in batches):
                available_product_names.append(p_name.capitalize())
                
        if not available_product_names:
            st.error("Нет товаров в наличии!")
        else:
            sel_display = st.selectbox("🔍 Выберите товар для продажи", sorted(available_product_names))
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
            total_sale_sum = sqty * custom_price
            
            if st.button("💵 Оформить продажу", type="primary"):
                st.session_state.show_confirmation = {
                    "p_key": p_key, "b_index": b_index, "name": sel_display, "batch_date": chosen_batch["date"],
                    "qty": sqty, "price": custom_price, "total": total_sale_sum, "payment": pay_method
                }

            if "show_confirmation" in st.session_state and st.session_state.show_confirmation:
                conf = st.session_state.show_confirmation
                
                @st.dialog("📋 Подтверждение операции")
                def confirm_dialog():
                    st.warning("Внимательно проверьте данные перед продажей:")
                    st.markdown(f"**Товар:** {conf['name']} (Поступление: {conf['batch_date']})")
                    st.markdown(f"**Количество:** {conf['qty']} шт. | **Цена:** {conf['price']:.2f} сом")
                    st.markdown(f"### Итого к оплате: {conf['total']:.2f} сом ({conf['payment']})")
                    
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
                            "total_sale": conf['total'], "total_cost": t_cost, 
                            "profit": conf['total'] - t_cost, "payment": conf['payment']
                        })
                        save_data(data)
                        st.session_state.show_confirmation = None
                        st.success("🎉 Продажа успешно проведена!")
                        st.rerun()
                    if col_no.button("❌ Отмена", type="secondary", use_container_width=True):
                        st.session_state.show_confirmation = None
                        st.rerun()
                confirm_dialog()

# --- НОВАЯ ВКЛАДКА 3: БАЛАНС КАССЫ ---
elif menu == "💵 Баланс Кассы":
    st.header("💵 Состояние кассы магазина")
    
    # Считаем продажи наличными и рассрочкой
    cash_from_sales = sum(s['total_sale'] for s in data["sales"] if s.get('payment') == 'Наличные')
    credit_from_sales = sum(s['total_sale'] for s in data["sales"] if s.get('payment') == 'Рассрочка')
    
    # Считаем ручные операции (инкассация или докладывание денег)
    manual_cash_flow = sum(op['amount'] for op in data.get('cash_operations', []))
    
    # Итого чистых наличных в кассе прямо сейчас
    current_cash_in_hand = cash_from_sales + manual_cash_flow
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе (сейчас)", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Сумма в рассрочке (долги)", f"{credit_from_sales:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль", f"{sum(s['profit'] for s in data['sales']):,.2f} сом")
    
    st.markdown("---")
    
    # Форма внесения/изъятия денег
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
        op_amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
        op_comment = st.text_input("Комментарий / Причина", placeholder="Например: взял на обед, доложил для сдачи")
        
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

# --- ВКЛАДКА 4: ОТЧЕТЫ ---
elif menu == "📊 Отчеты по дням":
    st.header("Аналитика и история продаж")
    if not data["sales"]:
        st.write("Продаж еще не было.")
    else:
        df = pd.DataFrame(data["sales"])
        df['day'] = pd.to_datetime(df['day']).dt.date
        
        st.subheader("🔍 Выберите период для просмотра отчета")
        today = datetime.now().date()
        date_range = st.date_input("Диапазон дат", value=(today, today))
        
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
            
            st.markdown("---")
            st.subheader("📋 Детализация продаж по типам оплаты")
            tab1, tab2, tab3 = st.tabs(["Все продажи", "💵 Наличные", "📝 Рассрочка"])
            
            def render_sales_table_with_actions(dataframe, tab_name):
                if dataframe.empty:
                    st.write("Нет операций за этот период.")
                    return
                
                h1, h2, h3, h4, h5, h6 = st.columns([2, 2.5, 1, 1.5, 1.5, 1.5])
                h1.markdown("**Дата/Время**")
                h2.markdown("**Товар (Партия)**")
                h3.markdown("**Кол-во**")
                h4.markdown("**Сумма**")
                h5.markdown("**Тип оплаты**")
                h6.markdown("**Действие**")
                st.markdown("---")
                
                for idx, row in dataframe.iloc[::-1].iterrows():
                    r1, r2, r3, r4, r5, r6 = st.columns([2, 2.5, 1, 1.5, 1.5, 1.5])
                    r1.write(row['date'])
                    r2.write(str(row['name']))
                    r3.write(f"{row['qty']} шт.")
                    r4.write(f"{row['total_sale']:.2f} сом")
                    r5.write(row.get('payment', 'Наличные'))
                    
                    button_key = f"del_{tab_name}_{row.get('id', idx)}"
                    if r6.button("❌ Отменить", key=button_key, type="secondary"):
                        st.session_state.show_sale_delete = {
                            "index_in_data_sales": idx, 
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
                        actual_idx = s_del["index_in_data_sales"]
                        sale_item = data["sales"][actual_idx]
                        
                        p_pure = sale_item.get("pure_name", None)
                        b_date = sale_item.get("batch_date", None)
                        
                        if p_pure and b_date:
                            if p_pure in data["products"]:
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
                        
                        data["sales"].pop(actual_idx)
                        save_data(data)
                        st.session_state.show_sale_delete = None
                        st.success("Продажа отменена, остаток на складе восстановлен!")
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
