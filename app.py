import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
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
st.title("🏬 Магазин «Сулайман-Тоо» — Учет и Рассрочки")

# Инициализация корзины покупок в сессии
if "cart" not in st.session_state:
    st.session_state.cart = []

# ==================== БОКОВАЯ ПАНЕЛЬ ====================
menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление", 
    "💰 Касса / Продажи", 
    "👥 База клиентов",
    "💵 Баланс Кассы",
    "📊 Отчеты по дням",
    "🧾 Оплата контрагентам"
])

st.sidebar.markdown("---")
st.sidebar.caption("Магазин Сулайман-Тоо • v5.0 (Supabase)")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
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
                    df = pd.read_csv(uploaded, encoding="utf-8")

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
                        st.success("Успешно сохранено!")
                        st.rerun()

        with col_edit:
            st.subheader("✏️ Редактировать / Удалить партию")
            if df_stock.empty:
                st.info("Товаров пока нет")
            else:
                options = {f"{row['Товар']} | Приход: {row['Дата поступления']} | Остаток: {row['В наличии (шт)']} шт.": row["id"] for _, row in df_stock.iterrows()}
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
                if st.button("🗑️ Да, удалить", type="primary", use_container_width=True):
                    supabase.table("products").delete().eq("id", db_id).execute()
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

# ==================== 💰 ВКЛАДКА 2: КАССА / ПРОДАЖИ (С КОРЗИНОЙ) ====================
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу (Корзина покупок)")
    stock_res = supabase.table("products").select("*").gt("qty", 0).execute()
    clients_res = supabase.table("clients").select("*").order("fio").execute()
    
    if not stock_res.data:
        st.warning("На складе нет доступных товаров для продажи")
    else:
        col_form, col_cart = st.columns([1.2, 1])
        
        with col_form:
            st.subheader("🛒 Выбор товаров")
            unique_names = sorted(list(set(row["name"].capitalize() for row in stock_res.data)))
            sel_display = st.selectbox("🔍 Выберите товар", unique_names)
            p_key = sel_display.lower()
            
            batches_options = {f"Поступление от {row['date']} (Остаток: {row['qty']} шт., Цена: {row['price']} сом)": row["id"] for row in stock_res.data if row["name"] == p_key}
            selected_batch_label = st.selectbox("📦 Выберите партию", list(batches_options.keys()))
            batch_id = batches_options[selected_batch_label]
            chosen_batch = supabase.table("products").select("*").eq("id", batch_id).execute().data[0]
            
            sqty = st.number_input("Количество для продажи (шт)", min_value=1, max_value=int(chosen_batch["qty"]), value=1)
            custom_price = st.number_input("💰 Цена продажи за 1 шт, сом", min_value=0.0, value=float(chosen_batch['price']))
            
            if st.button("➕ Добавить в чек", use_container_width=True):
                st.session_state.cart.append({
                    "batch_id": batch_id, "name": sel_display, "batch_date": chosen_batch["date"],
                    "qty": sqty, "price": custom_price, "total": sqty * custom_price, "cost": float(chosen_batch["cost"]), "pure_name": p_key
                })
                st.success(f"Товар {sel_display} добавлен в чек!")
                st.rerun()

        with col_cart:
            st.subheader("🧾 Текущий чек (Корзина)")
            if not st.session_state.cart:
                st.info("Чек пока пуст. Добавьте товары слева.")
                total_cart_sum = 0.0
            else:
                cart_df = pd.DataFrame(st.session_state.cart)
                st.dataframe(cart_df[["name", "qty", "price", "total"]], use_container_width=True, hide_index=True)
                total_cart_sum = cart_df["total"].sum()
                st.markdown(f"### 💵 Сумма по чеку: {total_cart_sum:,.2f} сом")
                if st.button("🗑️ Очистить чек"):
                    st.session_state.cart = []
                    st.rerun()

        if st.session_state.cart:
            st.markdown("---")
            st.subheader("💳 Параметры оплаты чека")
            pay_method = st.radio("Способ оплаты чека", ["Наличные", "Рассрочка"], horizontal=True)
            
            down_payment = 0.0
            months = 1
            client_id = None
            
            if pay_method == "Рассрочка":
                if not clients_res.data:
                    st.error("❌ В базе данных нет клиентов! Сначала добавьте клиента в разделе «База клиентов».")
                else:
                    client_opts = {f"{c['fio']} ({c['phone']})": c["id"] for c in clients_res.data}
                    sel_client = st.selectbox("👤 Выберите клиента из базы", list(client_opts.keys()))
                    client_id = client_opts[sel_client]
                    
                    c_r1, c_r2 = st.columns(2)
                    down_payment = c_r1.number_input("💵 Первоначальный взнос (наличные сейчас), сом", min_value=0.0, max_value=float(total_cart_sum), value=0.0)
                    months = c_r2.number_input("📅 Срок рассрочки (месяцев)", min_value=1, max_value=24, value=6)
            
            # Логика математики рассрочки
            net_debt = total_cart_sum - down_payment # Остаток долга ДО наценки
            markup_percent = months * 3 # 3% за каждый месяц
            markup_amount = net_debt * (markup_percent / 100) # Сумма наценки
            total_with_markup = net_debt + markup_amount # Итого долг С наценкой
            monthly_payment = round(total_with_markup / months) if months > 0 else 0 # Ежемесячный платеж

            if pay_method == "Рассрочка":
                st.info(f"💡 Расчет: Сумма чека {total_cart_sum} - Взнос {down_payment} = На остаток {net_debt} сом калькулируется наценка {markup_percent}% (+{markup_amount:.0f} сом). Всего в рассрочку: **{total_with_markup:.0f} сом**.")
                st.markdown(f"### 🔥 Ежемесячный платеж: **{monthly_payment:,.0f} сом / месяц** на {months} мес.")

            if st.button("🚀 Оформить и провести сделку", type="primary", use_container_width=True):
                # Проводим каждый товар из корзины в базу
                sale_group_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
                for item in st.session_state.cart:
                    # Уменьшаем склад
                    p_res = supabase.table("products").select("qty").eq("id", item["batch_id"]).execute().data[0]
                    new_qty = int(p_res["qty"]) - item["qty"]
                    supabase.table("products").update({"qty": new_qty}).eq("id", item["batch_id"]).execute()
                    
                    # Пишем продажу
                    t_cost = item["qty"] * item["cost"]
                    supabase.table("sales").insert({
                        "id": sale_group_id, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "day": datetime.now().strftime("%Y-%m-%d"),
                        "name": f"{item['name']} (приход {item['batch_date']})", "pure_name": item["pure_name"], "batch_date": item["batch_date"],
                        "qty": item["qty"], "total_sale": item["total"], "total_cost": t_cost, "profit": item["total"] - t_cost,
                        "payment": pay_method, "down_payment": down_payment if item == st.session_state.cart[0] else 0.0, # Пишем взнос только на первую запись чека
                        "credit_balance": total_with_markup if item == st.session_state.cart[0] else 0.0,
                        "client_id": client_id
                    }).execute()
                
                # Создаем график платежей в Supabase
                if pay_method == "Рассрочка" and client_id:
                    for m in range(1, months + 1):
                        due_date = (datetime.now() + timedelta(days=30 * m)).strftime("%Y-%m-%d")
                        supabase.table("credit_payments").insert({
                            "sale_id": sale_group_id, "client_id": client_id, "due_date": due_date,
                            "amount_expected": monthly_payment, "amount_paid": 0.0, "status": "Не оплачен"
                        }).execute()
                        
                st.session_state.cart = []
                st.success("🎉 Сделка и график платежей успешно зафиксированы в облаке Supabase!")
                st.rerun()

# ==================== 👥 НОВАЯ ВКЛАДКА 3: БАЗА КЛИЕНТОВ И РАССЧЕТЫ ====================
elif menu == "👥 База клиентов":
    st.header("👥 Управление клиентами и рассрочками")
    
    col_c1, col_c2 = st.columns([1, 1.5])
    with col_c1:
        st.subheader("➕ Регистрация нового клиента")
        with st.form("client_reg", clear_on_submit=True):
            fio = st.text_input("ФИО Клиента").strip()
            phone = st.text_input("Номер телефона").strip()
            passport = st.text_area("Паспортные данные (Серия, номер, кем выдан)").strip()
            if st.form_submit_button("Зарегистрировать"):
                if fio:
                    supabase.table("clients").insert({"fio": fio, "phone": phone, "passport": passport}).execute()
                    st.success("Клиент успешно добавлен в базу!")
                    st.rerun()
                    
    with col_c2:
        st.subheader("📋 Список клиентов в базе")
        c_all = supabase.table("clients").select("*").order("fio").execute()
        if not c_all.data:
            st.info("База клиентов пуста.")
        else:
            df_c = pd.DataFrame(c_all.data).drop(columns=["created_at"], errors="ignore")
            st.dataframe(df_c, use_container_width=True, hide_index=True)
            
    st.markdown("---")
    st.subheader("🔍 Карточка клиента и График платежей")
    if c_all.data:
        client_opts = {c["fio"]: c["id"] for c in c_all.data}
        selected_client_name = st.selectbox("Выберите клиента для просмотра задолженности", list(client_opts.keys()))
        c_id = client_opts[selected_client_name]
        
        # Загружаем график платежей этого клиента
        payments_res = supabase.table("credit_payments").select("*").eq("client_id", c_id).order("due_date").execute()
        
        if not payments_res.data:
            st.info("У этого клиента нет активных рассрочек.")
        else:
            st.markdown("### 📅 Календарный график платежей")
            df_p = pd.DataFrame(payments_res.data)
            
            # Показываем таблицу платежей с возможностью внести оплату
            for idx, row in df_p.iterrows():
                col_p1, col_p2, col_p3, col_p4 = st.columns([2, 2, 2, 1.5])
                col_p1.write(f"📅 Срок: **{row['due_date']}**")
                col_p2.write(f"💵 Должно быть: **{row['amount_expected']} сом**")
                col_p3.write(f"✅ Оплачено: **{row['amount_paid']} сом** ({row['status']})")
                
                if row['status'] != 'Оплачен':
                    pay_amount = col_p4.number_input("Внести сумму (сом)", min_value=0.0, max_value=float(row['amount_expected'] - row['amount_paid']), value=float(row['amount_expected'] - row['amount_paid']), key=f"pay_{row['id']}")
                    if col_p4.button("💳 Принять платеж", key=f"btn_{row['id']}"):
                        new_paid = float(row['amount_paid']) + pay_amount
                        new_status = "Оплачен" if new_paid >= float(row['amount_expected']) else "Частично"
                        
                        # Обновляем статус платежа
                        supabase.table("credit_payments").update({"amount_paid": new_paid, "status": new_status}).eq("id", row['id']).execute()
                        
                        # Автоматически добавляем эти деньги в кассу наличных
                        supabase.table("cash_operations").insert({
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "amount": pay_amount, "comment": f"Погашение рассрочки от {selected_client_name}"
                        }).execute()
                        
                        st.success("Платеж успешно принят в кассу!")
                        st.rerun()

# ==================== 💵 ВКЛАДКА 4: БАЛАНС КАССЫ ====================
elif menu == "💵 Баланс Кассы":
    st.header("💵 Состояние кассы магазина")
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance").execute()
    ops_res = supabase.table("cash_operations").select("amount").execute()
    
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    down_payments_cash = sum(float(s.get("down_payment", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    
    # Считаем сколько уже фактически оплачено по графикам
    paid_credits_res = supabase.table("credit_payments").select("amount_paid").execute()
    total_credit_collected = sum(float(p["amount_paid"]) for p in paid_credits_res.data)
    
    manual_cash_flow = sum(float(op['amount']) for op in ops_res.data)
    current_cash_in_hand = full_cash_sales + down_payments_cash + manual_cash_flow # Оплаты из графиков уже внутри manual_cash_flow
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе (сейчас в наличии)", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Чистый долг клиентов по рассрочкам", f"{credit_debts - total_credit_collected:,.2f} сом")
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
            st.success("Операция проведена!")
            st.rerun()

# ==================== 📊 ВКЛАДКА 5: ОТЧЕТЫ ====================
elif menu == "📊 Отчеты по дням":
    st.header("Аналитика и история продаж")
    sales_all = supabase.table("sales").select("*").execute()
    
    if not sales_all.data:
        st.write("Продаж еще не было.")
    else:
        df = pd.DataFrame(sales_all.data)
        df['day'] = pd.to_datetime(df['day']).dt.date
        
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

            st.markdown("---")
            st.subheader("📋 Детализация продаж")
            st.dataframe(filtered_df[["date", "name", "qty", "total_sale", "payment"]], use_container_width=True, hide_index=True)

# ==================== 🧾 ВКЛАДКА 6: ОПЛАТА КОНТРАГЕНТАМ ====================
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
    if payments_res.data:
        st.markdown("---")
        st.subheader("📜 История выплат контрагентам")
        df_pay = pd.DataFrame(payments_res.data).drop(columns=["id", "created_at"], errors="ignore")
        st.dataframe(df_pay, use_container_width=True, hide_index=True)

    # Скрытый блок полной очистки
    st.markdown("---")
    with st.expander("⚙️ Системные настройки (Очистка базы данных)"):
        confirm_check = st.checkbox("Я точно хочу удалить ВСЕ данные из Supabase")
        if st.button("🔥 Запустить полную очистку системы", type="secondary", disabled=not confirm_check):
            supabase.table("products").delete().neq("id", 0).execute()
            supabase.table("sales").delete().neq("id", "0").execute()
            supabase.table("cash_operations").delete().neq("id", 0).execute()
            supabase.table("supplier_payments").delete().neq("id", 0).execute()
            supabase.table("credit_payments").delete().neq("id", 0).execute()
            supabase.table("clients").delete().neq("id", 0).execute()
            st.success("Облачная база полностью сброшена!")
            st.rerun()
