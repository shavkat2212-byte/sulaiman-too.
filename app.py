import streamlit as st
import pandas as pd
from datetime import datetime
import io
from supabase import create_client, Client

# Инициализация подключения к Supabase через секреты Streamlit
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Ошибка подключения к Supabase. Проверьте Secrets в Streamlit! {e}")
    st.stop()

st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Облачный Учет")

# ==================== БОКОВАЯ ПАНЕЛЬ ====================
menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление", 
    "💰 Касса / Продажи", 
    "💵 Баланс Кассы",
    "📊 Отчеты по дням",
    "🧾 Оплата контрагентам"
])

st.sidebar.markdown("---")
st.sidebar.caption("Магазин Сулайман-Тоо • v4.0 (Supabase)")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ ====================
def db_get_stock():
    response = supabase.table("products").select("*").gt("qty", 0).execute()
    flat = []
    total_qty = total_cost = total_retail = 0.0
    
    for row in response.data:
        qty = int(row["qty"])
        cost = float(row["cost"])
        price = float(row["price"])
        flat.append({
            "id": row["id"],
            "Товар": str(row["name"]).capitalize(),
            "Дата поступления": row["date"],
            "В наличии (шт)": qty,
            "Закупка (сом)": cost,
            "Продажа (сом)": price,
            "Себестоимость партии (сом)": round(qty * cost, 2)
        })
        total_qty += qty
        total_cost += qty * cost
        total_retail += qty * price
    return pd.DataFrame(flat), total_qty, total_cost, total_retail

def db_save_product_smart(name, qty, cost, price, date_str):
    name = name.strip().lower()
    if not name:
        return False
    existing = supabase.table("products").select("*").eq("name", name).eq("date", date_str).execute()
    
    if existing.data:
        row_id = existing.data[0]["id"]
        supabase.table("products").update({"qty": qty, "cost": cost, "price": price}).eq("id", row_id).execute()
    else:
        supabase.table("products").insert({"name": name, "qty": qty, "cost": cost, "price": price, "date": date_str}).execute()
    return True

# ==================== 📦 ВКЛАДКА 1: СКЛАД ====================
if menu == "📦 Склад / Поступление":
    st.header("Управление складом")

    df_stock, total_qty, total_cost, total_retail = db_get_stock()

    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Всего товаров в наличии", f"{int(total_qty)} шт.")
    c2.metric("💰 Сумма склада в закупке", f"{total_cost:,.2f} сом")
    c3.metric("📈 Розничная стоимость склада", f"{total_retail:,.2f} сом")

    print_mode = st.checkbox("🖨️ Режим для печати отчёта")

    if print_mode:
        st.subheader("📄 ОТЧЁТ ПО ОСТАТКАМ ТОВАРОВ НА СКЛАДЕ")
        if not df_stock.empty:
            df_print = df_stock.copy().drop(columns=["id"], errors="ignore")
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
                        if db_save_product_smart(name, qty, cost, price, today):
                            imported += 1
                    except: continue
                if imported > 0:
                    st.success(f"🚀 Успешно загружено и сохранено в Supabase! Товаров: {imported}")
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
                if st.form_submit_button("Сохранить в облако"):
                    if name:
                        today = datetime.now().strftime("%Y-%m-%d")
                        db_save_product_smart(name, qty, cost, price, today)
                        st.success("Успешно отправлено в Supabase!")
                        st.rerun()

        with col_edit:
            st.subheader("✏️ Редактировать / Удалить партию")
            if df_stock.empty:
                st.info("Товаров пока нет")
            else:
                options = {}
                for _, row in df_stock.iterrows():
                    label = f"{row['Товар']} | Приход: {row['Дата поступления']} | Остаток: {row['В наличии (шт)']} шт."
                    options[label] = row["id"]

                selected = st.selectbox("Выберите запись для изменения", list(options.keys()))
                batch_id = options[selected]
                item_data = supabase.table("products").select("*").eq("id", batch_id).execute().data[0]

                with st.form("edit_form"):
                    new_qty = st.number_input("Изменить остаток (шт)", min_value=0, value=int(item_data["qty"]))
                    new_cost = st.number_input("Цена закупки, сом", min_value=0.0, value=float(item_data["cost"]))
                    new_price = st.number_input("Цена продажи, сом", min_value=0.0, value=float(item_data["price"]))

                    c_btn1, c_btn2 = st.columns(2)
                    if c_btn1.form_submit_button("💾 Сохранить изменения"):
                        supabase.table("products").update({"qty": new_qty, "cost": new_cost, "price": new_price}).eq("id", batch_id).execute()
                        st.success("Изменено в базе!")
                        st.rerun()

                    if c_btn2.form_submit_button("🗑️ Удалить партию", type="secondary"):
                        st.session_state.delete_batch_id = batch_id
                        st.session_state.delete_batch_label = selected
                        st.rerun()

        if "delete_batch_id" in st.session_state and st.session_state.delete_batch_id:
            db_id = st.session_state.delete_batch_id
            @st.dialog("⚠️ Подтверждение удаления")
            def delete_batch_dialog():
                st.error(f"Удалить выбранную партию из базы?\n{st.session_state.delete_batch_label}")
                col_y, col_n = st.columns(2)
                if col_y.button("🗑️ Да, удалить", type="primary", use_container_width=True):
                    supabase.table("products").delete().eq("id", db_id).execute()
                    st.session_state.delete_batch_id = None
                    st.success("Удалено из облака!")
                    st.rerun()
                if col_n.button("Отмена", type="secondary", use_container_width=True):
                    st.session_state.delete_batch_id = None
                    st.rerun()
            delete_batch_dialog()

        st.markdown("---")
        st.subheader("📋 Список всех товаров на складе")
        if not df_stock.empty:
            df_display = df_stock.copy().drop(columns=["id"], errors="ignore")
            df_display["Закупка (сом)"] = df_display["Закупка (сом)"].map('{:,.2f} сом'.format)
            df_display["Продажа (сом)"] = df_display["Продажа (сом)"].map('{:,.2f} сом'.format)
            df_display["Себестоимость партии (сом)"] = df_display["Себестоимость партии (сом)"].map('{:,.2f} сом'.format)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

# ==================== 💰 ВКЛАДКА 2: КАССА / ПРОДАЖИ ====================
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу")
    stock_res = supabase.table("products").select("*").gt("qty", 0).execute()
    
    if not stock_res.data:
        st.warning("На складе нет доступных товаров для продажи")
    else:
        unique_names = sorted(list(set(row["name"].capitalize() for row in stock_res.data)))
        sel_display = st.selectbox("🔍 Выберите товар для продажи", unique_names)
        p_key = sel_display.lower()
        
        batches_options = {}
        for row in stock_res.data:
            if row["name"] == p_key:
                batches_options[f"Поступление от {row['date']} (Остаток: {row['qty']} шт., Цена: {row['price']} сом)"] = row["id"]
                
        selected_batch_label = st.selectbox("📦 С какой даты поступления списать товар?", list(batches_options.keys()))
        batch_id = batches_options[selected_batch_label]
        chosen_batch = supabase.table("products").select("*").eq("id", batch_id).execute().data[0]
        
        sqty = st.number_input("Количество для продажи (шт)", min_value=1, max_value=int(chosen_batch["qty"]), value=1)
        custom_price = st.number_input("💰 Цена продажи за 1 шт (можно изменить), сом", min_value=0.0, value=float(chosen_batch['price']))
        pay_method = st.radio("💳 Способ оплаты", ["Наличные", "Рассрочка"], horizontal=True)
        
        down_payment = 0.0
        total_sale_sum = sqty * custom_price
        if pay_method == "Рассрочка":
            down_payment = st.number_input("💵 Первоначальный взнос (в кассу наличными), сом", min_value=0.0, max_value=float(total_sale_sum), value=0.0, step=100.0)
        credit_balance = total_sale_sum - down_payment

        if st.button("💵 Оформить продажу", type="primary"):
            st.session_state.show_confirmation = {
                "batch_id": batch_id, "p_key": p_key, "name": sel_display, "batch_date": chosen_batch["date"],
                "qty": sqty, "price": custom_price, "total": total_sale_sum, "payment": pay_method,
                "down_payment": down_payment, "credit_balance": credit_balance, "cost": float(chosen_batch["cost"])
            }

        if "show_confirmation" in st.session_state and st.session_state.show_confirmation:
            conf = st.session_state.show_confirmation
            @st.dialog("📋 Подтверждение операции")
            def confirm_dialog():
                st.warning("Внимательно проверьте данные перед продажей:")
                st.markdown(f"**Товар:** {conf['name']} (Поступление: {conf['batch_date']})")
                st.markdown(f"**Количество:** {conf['qty']} шт. | **Цена за шт:** {conf['price']:.2f} сом")
                st.markdown(f"### Общая сумма сделки: {conf['total']:.2f} сом")
                
                if conf['payment'] == "Рассрочка":
                    st.markdown(f"**Способ оплаты:** 📝 Рассрочка")
                    st.markdown(f"👉 **Вносится наличными сейчас:** {conf['down_payment']:.2f} сом")
                    st.markdown(f"👉 **Остаток долга в рассрочку:** {conf['credit_balance']:.2f} сом")
                else:
                    st.markdown(f"**Способ оплаты:** 💵 Полные Наличные")
                
                col_yes, col_no = st.columns(2)
                if col_yes.button("✅ Да, подтверждаю продажу", type="primary", use_container_width=True):
                    # Списываем со склада
                    new_q = int(chosen_batch["qty"]) - conf["qty"]
                    supabase.table("products").update({"qty": new_q}).eq("id", conf["batch_id"]).execute()
                    
                    # Пишем продажу
                    sale_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
                    t_cost = conf["qty"] * conf["cost"]
                    
                    supabase.table("sales").insert({
                        "id": sale_id, "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "day": datetime.now().strftime("%Y-%m-%d"), "name": f"{conf['name']} (приход {conf['batch_date']})",
                        "pure_name": conf["p_key"], "batch_date": conf["batch_date"], "qty": conf["qty"],
                        "total_sale": conf["total"], "total_cost": t_cost, "profit": conf["total"] - t_cost,
                        "payment": conf["payment"], "down_payment": conf["down_payment"], "credit_balance": conf["credit_balance"]
                    }).execute()
                    
                    st.session_state.show_confirmation = None
                    st.success("🎉 Продажа сохранена в Supabase!")
                    st.rerun()
                if col_no.button("❌ Отмена", type="secondary", use_container_width=True):
                    st.session_state.show_confirmation = None
                    st.rerun()
            confirm_dialog()

# ==================== 💵 ВКЛАДКА 3: БАЛАНС КАССЫ ====================
elif menu == "💵 Баланс Кассы":
    st.header("💵 Состояние кассы магазина")
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance").execute()
    ops_res = supabase.table("cash_operations").select("amount").execute()
    
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    down_payments_cash = sum(float(s.get("down_payment", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    
    manual_cash_flow = sum(float(op['amount']) for op in ops_res.data)
    current_cash_in_hand = full_cash_sales + down_payments_cash + manual_cash_flow
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе (включая взносы)", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Чистый долг в рассрочке", f"{credit_debts:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль магазина", f"{sum(float(s['profit']) for s in sales_res.data):,.2f} сом")
    
    st.markdown("---")
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
        comment = st.text_input("Комментарий / Причина")
        
        if st.form_submit_button("Выполнить операцию"):
            actual = amount if "Положить" in op_type else -amount
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "amount": actual, "comment": comment or op_type
            }).execute()
            st.success("Операция по кассе успешно записана!")
            st.rerun()
            
    history_res = supabase.table("cash_operations").select("*").order("id", desc=True).limit(20).execute()
    if history_res.data:
        st.markdown("---")
        st.subheader("📜 История движений по кассе (Последние 20)")
        df_ops = pd.DataFrame(history_res.data).drop(columns=["id", "created_at"], errors="ignore")
        st.dataframe(df_ops, use_container_width=True, hide_index=True)

# ==================== 📊 ВКЛАДКА 4: ОТЧЕТЫ ====================
elif menu == "📊 Отчеты по дням":
    st.header("Аналитика и история продаж")
    sales_all = supabase.table("sales").select("*").execute()
    
    if not sales_all.data:
        st.write("Продаж еще не было.")
    else:
        df = pd.DataFrame(sales_all.data)
        df['day'] = pd.to_datetime(df['day']).dt.date
        
        st.subheader("🔍 Выберите период для просмотра отчета")
        date_range = st.date_input("Диапазон дат", value=(df['day'].min(), df['day'].max()))
        
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[(df['day'] >= start_date) & (df['day'] <= end_date)]
        else: filtered_df = df
            
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
                st.download_button("Нажмите здесь для загрузки файла", data=output.getvalue(), file_name=f"report_{datetime.now().strftime('%Y%m%d')}.xlsx")

            st.markdown("---")
            st.subheader("📋 Таблицы детализации продаж за период")
            tab1, tab2, tab3 = st.tabs(["Все продажи", "💵 Наличные", "📝 Рассрочка"])
            
            def render_sales_table_simple(dataframe, tab_name):
                if dataframe.empty:
                    st.write("Нет операций за этот период.")
                    return
                if tab_name == "credit":
                    h1, h2, h3, h4, h5, h6 = st.columns([2, 3, 1, 1.5, 1.5, 1.5])
                    h1.markdown("**Дата/Время**")
                    h2.markdown("**Товар**")
                    h3.markdown("**Кол-во**")
                    h4.markdown("**Итого цена**")
                    h5.markdown("**Перв. взнос**")
                    h6.markdown("**Остаток долга**")
                    st.markdown("---")
                    for _, row in dataframe.iloc[::-1].iterrows():
                        r1, r2, r3, r4, r5, r6 = st.columns([2, 3, 1, 1.5, 1.5, 1.5])
                        r1.write(row['date'])
                        r2.write(str(row['name']))
                        r3.write(f"{row['qty']} шт.")
                        r4.write(f"{float(row['total_sale']):,.2f} c.")
                        r5.write(f"{float(row.get('down_payment', 0.0)):,.2f} c.")
                        r6.write(f"{float(row.get('credit_balance', row['total_sale'])):,.2f} c.")
                else:
                    h1, h2, h3, h4, h5 = st.columns([2, 3, 1, 2, 2])
                    h1.markdown("**Дата/Время**")
                    h2.markdown("**Товар (Партия)**")
                    h3.markdown("**Кол-во**")
                    h4.markdown("**Сумма сделки**")
                    h5.markdown("**Тип оплаты**")
                    st.markdown("---")
                    for _, row in dataframe.iloc[::-1].iterrows():
                        r1, r2, r3, r4, r5 = st.columns([2, 3, 1, 2, 2])
                        r1.write(row['date'])
                        r2.write(str(row['name']))
                        r3.write(f"{row['qty']} шт.")
                        r4.write(f"{float(row['total_sale']):,.2f} c.")
                        r5.write(row.get('payment', 'Наличные'))

            with tab1: render_sales_table_simple(filtered_df, "all")
            with tab2: render_sales_table_simple(filtered_df[filtered_df['payment'] == 'Наличные'], "cash")
            with tab3: render_sales_table_simple(filtered_df[filtered_df['payment'] == 'Рассрочка'], "credit")

            # БЛОК РЕДАКТИРОВАНИЯ В САМОМ НИЗУ СТРАНИЦЫ
            st.markdown("---")
            st.subheader("✏️ Редактировать или Отменить продажу из детализации")
            sales_options = {}
            for idx, s in enumerate(sales_all.data):
                label = f"[{s['date']}] {s['name'].capitalize()} — {s['qty']}шт = {float(s['total_sale']):.0f} сом ({s['payment']})"
                sales_options[label] = idx
            
            selected_sale_label = st.selectbox("Выберите операцию из списка для исправления/удаления", list(sales_options.keys()))
            target_sale_idx = sales_options[selected_sale_label]
            sale_to_edit = sales_all.data[target_sale_idx]
            
            with st.form("edit_sale_form"):
                col_e1, col_e2, col_e3, col_e4 = st.columns(4)
                old_qty = int(sale_to_edit["qty"])
                old_price_one = float(sale_to_edit["total_sale"] / old_qty)
                
                new_s_qty = col_e1.number_input("Исправить Количество (шт)", min_value=1, value=old_qty)
                new_s_price = col_e2.number_input("Исправить Цену за 1 шт (сом)", min_value=0.0, value=old_price_one)
                new_s_payment = col_e3.selectbox("Способ оплаты", ["Наличные", "Рассрочка"], index=0 if sale_to_edit["payment"] == "Наличные" else 1)
                
                new_total_sum = new_s_qty * new_s_price
                new_s_down = 0.0
                if new_s_payment == "Рассрочка":
                    old_down = float(sale_to_edit.get("down_payment", 0.0))
                    new_s_down = col_e4.number_input("Первоначальный взнос (сом)", min_value=0.0, max_value=float(new_total_sum), value=min(old_down, new_total_sum))
                
                new_credit_balance = new_total_sum - new_s_down
                
                btn_save_sale, btn_del_sale = st.columns(2)
                click_save = btn_save_sale.form_submit_button("💾 Сохранить изменения в продаже", type="primary")
                click_del = btn_del_sale.form_submit_button("❌ Полностью отменить эту продажу", type="secondary")
                
                if click_save:
                    st.session_state.pending_edit_sale = {
                        "id": sale_to_edit["id"], "old_qty": old_qty, "new_qty": new_s_qty,
                        "new_price": new_s_price, "new_total": new_total_sum, "payment": new_s_payment,
                        "down_payment": new_s_down, "credit_balance": new_credit_balance,
                        "pure_name": sale_to_edit["pure_name"], "batch_date": sale_to_edit["batch_date"],
                        "total_cost": float(sale_to_edit["total_cost"])
                    }
                    st.rerun()
                
                if click_del:
                    st.session_state.show_sale_delete = {
                        "sale_id": sale_to_edit["id"], "name": sale_to_edit['name'], "qty": sale_to_edit['qty'], 
                        "total": sale_to_edit['total_sale'], "pure_name": sale_to_edit["pure_name"], "batch_date": sale_to_edit["batch_date"]
                    }
                    st.rerun()

            # ПОП-АП диалог подтверждения редактирования
            if "pending_edit_sale" in st.session_state and st.session_state.pending_edit_sale:
                pe = st.session_state.pending_edit_sale
                @st.dialog("📋 Подтверждение изменения продажи")
                def confirm_edit_dialog():
                    st.warning("Внимательно проверьте исправленные данные:")
                    st.markdown(f"### Новая сумма сделки: {pe['new_total']:.2f} сом ({pe['payment']})")
                    if pe['payment'] == "Рассрочка":
                        st.markdown(f"👉 **Взнос:** {pe['down_payment']:.2f} сом | **Долг:** {pe['credit_balance']:.2f} сом")
                    
                    col_y, col_n = st.columns(2)
                    if col_y.button("✅ Да, сохранить изменения", type="primary", use_container_width=True):
                        qty_diff = pe["new_qty"] - pe["old_qty"]
                        
                        # Обновляем склад в Supabase
                        exist_b = supabase.table("products").select("*").eq("name", pe["pure_name"]).eq("date", pe["batch_date"]).execute()
                        if exist_b.data:
                            new_stock = int(exist_b.data[0]["qty"]) - qty_diff
                            supabase.table("products").update({"qty": new_stock}).eq("id", exist_b.data[0]["id"]).execute()
                        
                        single_cost = pe["total_cost"] / pe["old_qty"]
                        new_cost = pe["new_qty"] * single_cost
                        
                        # Пишем изменения в Supabase
                        supabase.table("sales").update({
                            "qty": pe["new_qty"], "total_sale": pe["new_total"], "total_cost": new_cost,
                            "profit": pe["new_total"] - new_cost, "payment": pe["payment"],
                            "down_payment": pe["down_payment"], "credit_balance": pe["credit_balance"]
                        }).eq("id", pe["id"]).execute()
                        
                        st.session_state.pending_edit_sale = None
                        st.success("Изменения записаны в Supabase!")
                        st.rerun()
                    if col_n.button("Отмена", type="secondary", use_container_width=True):
                        st.session_state.pending_edit_sale = None
                        st.rerun()
                confirm_edit_dialog()

            # ПОП-АП диалог удаления
            if "show_sale_delete" in st.session_state and st.session_state.show_sale_delete:
                s_del = st.session_state.show_sale_delete
                @st.dialog("⚠️ Отмена и удаление продажи")
                def delete_sale_dialog():
                    st.error("Отменить эту сделку в Supabase?")
                    col_y, col_n = st.columns(2)
                    if col_y.button("🔥 Да, отменить", type="primary", use_container_width=True):
                        # Возвращаем на склад
                        exist_b = supabase.table("products").select("*").eq("name", s_del["pure_name"]).eq("date", s_del["batch_date"]).execute()
                        if exist_b.data:
                            new_stock = int(exist_b.data[0]["qty"]) + int(s_del["qty"])
                            supabase.table("products").update({"qty": new_stock}).eq("id", exist_b.data[0]["id"]).execute()
                        
                        # Стираем продажу
                        supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                        st.session_state.show_sale_delete = None
                        st.success("Удалено из облака!")
                        st.rerun()
                    if col_n.button("Назад", type="secondary", use_container_width=True):
                        st.session_state.show_sale_delete = None
                        st.rerun()
                delete_sale_dialog()

# ==================== 🧾 ВКЛАДКА 5: ОПЛАТА КОНТРАГЕНТАМ ====================
elif menu == "🧾 Оплата контрагентам":
    st.header("Выплаты поставщикам и контрагентам")
    st.subheader("📤 Зафиксировать выплату")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента / поставщика")
        amount = st.number_input("Сумма выплаты (сом)", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий / Назначение платежа")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                supabase.table("supplier_payments").insert({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "supplier": supplier.strip(), "amount": amount, "comment": comment
                }).execute()
                st.success("Выплата отправлена в Supabase!")
                st.rerun()

    payments_res = supabase.table("supplier_payments").select("*").order("id", desc=True).execute()
    st.markdown("---")
    st.subheader("📜 История выплат контрагентам")
    if not payments_res.data:
        st.info("Выплат ещё не было")
    else:
        df_pay = pd.DataFrame(payments_res.data).drop(columns=["id", "created_at"], errors="ignore")
        df_display_pay = df_pay.copy()
        df_display_pay["amount"] = df_display_pay["amount"].map('{:,.2f} сом'.format)
        st.dataframe(df_display_pay, use_container_width=True, hide_index=True)
        
        total_paid = sum(float(p["amount"]) for p in payments_res.data)
        st.metric("Всего выплачено контрагентам", f"{total_paid:,.2f} сом")

    # Скрытый блок полной очистки (теперь чистит Supabase)
    st.markdown("---")
    with st.expander("⚙️ Системные настройки (Очистка базы данных)"):
        st.warning("Внимание! Очистит все таблицы в облаке Supabase.")
        confirm_check = st.checkbox("Я точно хочу удалить ВСЕ данные из Supabase")
        if st.button("🔥 Запустить полную очистку системы", type="secondary", disabled=not confirm_check):
            supabase.table("products").delete().neq("id", 0).execute()
            supabase.table("sales").delete().neq("id", "0").execute()
            supabase.table("cash_operations").delete().neq("id", 0).execute()
            supabase.table("supplier_payments").delete().neq("id", 0).execute()
            st.success("Облачная база полностью сброшена!")
            st.rerun()
