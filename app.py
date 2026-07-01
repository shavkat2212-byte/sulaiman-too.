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
st.sidebar.caption("Магазин Сулайман-Тоо • v6.3 (Cash Ledger Fixed)")

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
        st.write("💡 Порядок столбцов в файле: **Название товара | Количество | Цена закупки | Цена продажи**")
        uploaded = st.file_uploader("Шаг 1: Выберите файл вашей таблицы на телефоне/компьютере", type=["csv", "xlsx"])
        
        if uploaded is not None:
            st.info(f"📁 Файл «{uploaded.name}» успешно выбран.")
            if st.button("🚀 Шаг 2: Загрузить товары из этого файла на склад", type="primary", use_container_width=True):
                with st.spinner("⏳ Синхронизация с облаком Supabase... Пожалуйста, подождите."):
                    try:
                        if uploaded.name.endswith(".xlsx"):
                            df = pd.read_excel(uploaded, engine="openpyxl")
                        else:
                            try:
                                df = pd.read_csv(uploaded, encoding="utf-8")
                            except:
                                uploaded.seek(0)
                                df = pd.read_csv(uploaded, sep=None, engine="python", encoding="cp1251")

                        today = datetime.now().strftime("%Y-%m-%d")
                        
                        existing_res = supabase.table("products").select("id", "name").eq("date", today).execute()
                        existing_map = {row["name"]: row["id"] for row in existing_res.data}
                        
                        insert_list = []
                        for idx, row in df.iterrows():
                            try:
                                name_raw = str(row.iloc[0]).strip().lower()
                                if not name_raw or name_raw == "nan": continue
                                qty_raw = int(float(str(row.iloc[1]).replace(" ", "").replace(",", ".")))
                                cost_raw = float(str(row.iloc[2]).replace(" ", "").replace(",", "."))
                                price_raw = float(str(row.iloc[3]).replace(" ", "").replace(",", "."))
                                
                                if name_raw in existing_map:
                                    supabase.table("products").update({
                                        "qty": qty_raw, "cost": cost_raw, "price": price_raw
                                    }).eq("id", existing_map[name_raw]).execute()
                                else:
                                    insert_list.append({
                                        "name": name_raw, "qty": qty_raw, "cost": cost_raw, "price": price_raw, "date": today
                                    })
                            except:
                                continue
                        
                        if insert_list:
                            supabase.table("products").insert(insert_list).execute()
                            
                        st.success("🎉 Облачный склад Supabase успешно синхронизирован!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Произошла ошибка при чтении или отправке файла: {e}")

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
                        existing = supabase.table("products").select("*").eq("name", name).eq("date", today).execute()
                        if existing.data:
                            supabase.table("products").update({"qty": qty, "cost": cost, "price": price}).eq("id", existing.data[0]["id"]).execute()
                        else:
                            supabase.table("products").insert({"name": name, "qty": qty, "cost": cost, "price": price, "date": today}).execute()
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

# ==================== 💰 ВКЛАДКА 2: КАССА / ПРОДАЖИ ====================
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
            sale_date = st.date_input("📅 Дата продажи (можно изменить для ввода задним числом)", value=datetime.now().date())
            pay_method = st.radio("Способ оплаты чека", ["Наличные", "Рассрочка"], horizontal=True)
            
            down_payment = 0.0
            months = 1
            client_id = None
            sel_client_name = ""
            
            if pay_method == "Рассрочка":
                if not clients_res.data:
                    st.error("❌ В базе данных нет клиентов! Сначала добавьте клиента в разделе «База клиентов».")
                else:
                    client_opts = {f"{c['fio']} ({c['phone']})": c for c in clients_res.data}
                    sel_client_label = st.selectbox("👤 Выберите клиента из базы", list(client_opts.keys()))
                    client_id = client_opts[sel_client_label]["id"]
                    sel_client_name = client_opts[sel_client_label]["fio"]
                    
                    c_r1, c_r2 = st.columns(2)
                    down_payment = c_r1.number_input("💵 Первоначальный взнос (наличные сейчас), сом", min_value=0.0, max_value=float(total_cart_sum), value=0.0)
                    months = c_r2.number_input("📅 Срок рассрочки (месяцев)", min_value=1, max_value=24, value=6)
            
            net_debt = total_cart_sum - down_payment
            markup_percent = months * 3
            markup_amount = net_debt * (markup_percent / 100)
            total_with_markup = net_debt + markup_amount
            monthly_payment = round(total_with_markup / months) if months > 0 else 0

            if pay_method == "Рассрочка":
                st.info(f"💡 Расчет: Сумма чека {total_cart_sum} - Взнос {down_payment} = На остаток {net_debt} сом калькулируется наценка {markup_percent}% (+{markup_amount:.0f} сом). Всего в рассрочку: **{total_with_markup:.0f} сом**.")
                st.markdown(f"### 🔥 Ежемесячный платеж: **{monthly_payment:,.0f} сом / месяц** на {months} мес.")

            if st.button("🚀 Оформить и провести сделку", type="primary", use_container_width=True):
                sale_group_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
                day_str = sale_date.strftime("%Y-%m-%d")
                date_full_str = f"{day_str} {datetime.now().strftime('%H:%M')}"
                
                try:
                    # 1. СПИСЫВАЕМ ТОВАРЫ СО СКЛАДА
                    total_cost_sum = 0.0
                    items_list_str = []
                    for item in st.session_state.cart:
                        p_res = supabase.table("products").select("qty").eq("id", item["batch_id"]).execute().data[0]
                        new_qty = int(p_res["qty"]) - item["qty"]
                        supabase.table("products").update({"qty": new_qty}).eq("id", item["batch_id"]).execute()
                        total_cost_sum += (item["qty"] * item["cost"])
                        items_list_str.append(f"{item['name']} ({item['qty']} шт.)")
                    
                    goods_summary = ", ".join(items_list_str)
                    
                    # 2. ЗАПИСЫВАЕМ В ТАБЛИЦУ ПРОДАЖ
                    if pay_method == "Наличные":
                        for item in st.session_state.cart:
                            t_cost = item["qty"] * item["cost"]
                            supabase.table("sales").insert({
                                "id": sale_group_id, "date": date_full_str, "day": day_str,
                                "name": f"{item['name']} (приход {item['batch_date']})", "pure_name": item["pure_name"], "batch_date": item["batch_date"],
                                "qty": item["qty"], "total_sale": int(item["total"]), "total_cost": int(t_cost), "profit": int(item["total"] - t_cost),
                                "payment": "Наличные", "down_payment": 0, "credit_balance": 0, "client_id": None
                            }).execute()
                    else:
                        contract_name = f"Договор рассрочки №{sale_group_id[:6]} [{goods_summary}] — {sel_client_name}"
                        total_profit = total_cart_sum - total_cost_sum
                        
                        supabase.table("sales").insert({
                            "id": sale_group_id, "date": date_full_str, "day": day_str,
                            "name": contract_name, "pure_name": "рассрочка", "batch_date": day_str,
                            "qty": 1, "total_sale": int(total_cart_sum), "total_cost": int(total_cost_sum), "profit": int(total_profit),
                            "payment": "Рассрочка", "down_payment": int(down_payment), "credit_balance": int(total_with_markup), "client_id": client_id
                        }).execute()
                    
                    # 3. Формируем график платежей
                    if pay_method == "Рассрочка" and client_id:
                        for m in range(1, months + 1):
                            due_date = (sale_date + timedelta(days=30 * m)).strftime("%Y-%m-%d")
                            try:
                                supabase.table("credit_payments").insert({
                                    "sale_id": sale_group_id, "client_id": client_id, "due_date": due_date,
                                    "amount_expected": int(monthly_payment), "amount_paid": 0, "status": "Не оплачен"
                                }).execute()
                            except:
                                continue
                                
                    st.session_state.cart = []
                    st.success(f"🎉 Сделка успешно проведена датой {day_str}!")
                    st.rerun()
                    
                except Exception as e_global:
                    st.error(f"⚠️ Ошибка базы данных при записи продажи: {e_global}.")

# ==================== 👥 ВКАЛАДКА 3: БАЗА КЛИЕНТОВ ====================
elif menu == "👥 База клиентов":
    st.header("👥 Управление клиентами и рассрочками")
    c_all = supabase.table("clients").select("*").order("fio").execute()
    
    col_c1, col_c2 = st.columns([1, 1.2])
    with col_c1:
        st.subheader("➕ Регистрация нового клиента")
        with st.form("client_reg", clear_on_submit=True):
            fio = st.text_input("ФИО Клиента").strip()
            phone = st.text_input("Номер телефона").strip()
            address = st.text_input("Адрес проживания").strip()
            passport = st.text_area("Паспортные данные").strip()
            if st.form_submit_button("Зарегистрировать"):
                if fio:
                    supabase.table("clients").insert({
                        "fio": fio, "phone": phone if phone else None, 
                        "address": address if address else None, "passport": passport if passport else None
                    }).execute()
                    st.success("Клиент успешно добавлен в базу!")
                    st.rerun()
                    
    with col_c2:
        st.subheader("✏️ Редактировать данные клиента")
        if not c_all.data:
            st.info("В базе пока нет клиентов для редактирования.")
        else:
            client_edit_opts = {c["fio"]: c for c in c_all.data}
            selected_edit_name = st.selectbox("Выберите клиента для изменения данных", list(client_edit_opts.keys()))
            client_to_update = client_edit_opts[selected_edit_name]
            
            with st.form("client_edit_form"):
                new_fio = st.text_input("Изменить ФИО", value=str(client_to_update["fio"]))
                new_phone = st.text_input("Изменить телефон", value=str(client_to_update["phone"] or ""))
                new_address = st.text_input("Изменить адрес", value=str(client_to_update.get("address") or ""))
                new_passport = st.text_area("Изменить паспортные данные", value=str(client_to_update["passport"] or ""))
                
                if st.form_submit_button("💾 Сохранить изменения в карточке"):
                    if new_fio:
                        supabase.table("clients").update({
                            "fio": new_fio.strip(),
                            "phone": new_phone.strip() if new_phone.strip() else None,
                            "address": new_address.strip() if new_address.strip() else None,
                            "passport": new_passport.strip() if new_passport.strip() else None
                        }).eq("id", client_to_update["id"]).execute()
                        st.success("Данные клиента успешно обновлены!")
                        st.rerun()

    st.markdown("---")
    st.subheader("📋 Список всех клиентов в базе")
    if not c_all.data:
        st.info("База клиентов пуста.")
    else:
        df_c = pd.DataFrame(c_all.data).drop(columns=["created_at"], errors="ignore")
        df_c = df_c.rename(columns={"id": "ID", "fio": "ФИО Клиента", "phone": "Телефон", "address": "Адрес проживания", "passport": "Паспортные данные"})
        if "Адрес проживания" not in df_c.columns:
            df_c["Адрес проживания"] = None
            
        st.dataframe(df_c[["ID", "ФИО Клиента", "Телефон", "Адрес проживания", "Паспортные данные"]], use_container_width=True, hide_index=True)
            
    st.markdown("---")
    st.subheader("🔍 Карточка рассрочки, История покупок и Прием оплаты")
    if c_all.data:
        client_opts = {c["fio"]: c["id"] for c in c_all.data}
        selected_client_name = st.selectbox("Выберите клиента из списка для просмотра деталей", list(client_opts.keys()))
        c_id = client_opts[selected_client_name]
        
        # Показываем историю взятых товаров/договоров клиента
        st.markdown("### 📦 История купленных товаров / Договоров")
        client_sales_res = supabase.table("sales").select("*").eq("client_id", c_id).order("date").execute()
        if not client_sales_res.data:
            st.info("У этого клиента пока нет оформленных договоров купли-продажи.")
        else:
            for s_row in client_sales_res.data:
                st.markdown(f"🔹 **{s_row['date']}** — {s_row['name']} | Сумма: **{s_row['total_sale']} сом** (Взнос: {s_row['down_payment']} сом, Долг: {s_row['credit_balance']} сом)")

        # Календарный график платежей
        payments_res = supabase.table("credit_payments").select("*").eq("client_id", c_id).order("due_date").execute()
        
        if not payments_res.data:
            st.info("У этого клиента нет активных задолженностей по рассрочке.")
        else:
            st.markdown("### 📅 Календарный график платежей")
            df_p = pd.DataFrame(payments_res.data)
            
            for idx, row in df_p.iterrows():
                col_p1, col_p2, col_p3, col_p4 = st.columns([2, 2, 2, 2])
                col_p1.write(f"📅 Срок: **{row['due_date']}**")
                col_p2.write(f"💵 Должно быть: **{row['amount_expected']} сом**")
                col_p3.write(f"✅ Оплачено: **{row['amount_paid']} сом** ({row['status']})")
                
                if row['status'] != 'Оплачен':
                    pay_amount = col_p4.number_input(
                        "Сумма оплаты (вручную)", 
                        min_value=0.0, 
                        value=float(row['amount_expected'] - row['amount_paid']), 
                        key=f"pay_{row['id']}"
                    )
                    if col_p4.button("💳 Принять платеж", key=f"btn_{row['id']}", use_container_width=True):
                        new_paid = float(row['amount_paid']) + pay_amount
                        new_status = "Оплачен" if new_paid >= float(row['amount_expected']) else "Частично"
                        
                        supabase.table("credit_payments").update({"amount_paid": new_paid, "status": new_status}).eq("id", row['id']).execute()
                        
                        supabase.table("cash_operations").insert({
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "amount": pay_amount, "comment": f"Погашение рассрочки от {selected_client_name}"
                        }).execute()
                        
                        st.success("Платеж успешно принят и зачислен в кассу!")
                        st.rerun()

# ==================== 💵 ВКЛАДКА 4: БАЛАНС КАССЫ ====================
elif menu == "💵 Баланс Кассы":
    st.header("💵 Состояние кассы магазина")
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    down_payments_cash = sum(float(s.get("down_payment", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    
    paid_credits_res = supabase.table("credit_payments").select("amount_paid").execute()
    total_credit_collected = sum(float(p["amount_paid"]) for p in paid_credits_res.data)
    
    manual_cash_flow = sum(float(op['amount']) for op in ops_res.data)
    current_cash_in_hand = full_cash_sales + down_payments_cash + manual_cash_flow
    
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

    # 📑 НОВОЕ: ОТЧЕТ ПО РАСХОДАМ И ВНЕСЕНИЯМ ИЗ КАССЫ
    st.markdown("---")
    st.subheader("📜 История кассовых операций (Внесения и изъятия)")
    if not ops_res.data:
        st.info("Ручных операций по кассе еще не проводилось.")
    else:
        df_ops = pd.DataFrame(ops_res.data)
        # Красивое переименование столбцов для пользователя
        df_ops = df_ops.rename(columns={
            "date": "Дата и время",
            "amount": "Сумма (сом)",
            "comment": "Назначение / Комментарий"
        })
        # Сортируем колонки и убираем id
        cols_to_show = ["Дата и время", "Сумма (сом)", "Назначение / Комментарий"]
        st.dataframe(df_ops[cols_to_show], use_container_width=True, hide_index=True)

# ==================== 📊 ВКЛАДКА 5: ОТЧЕТЫ ====================
elif menu == "📊 Отчеты по дням":
    st.header("📊 Аналитика и история продаж")
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
            revenue_cash = filtered_df[filtered_df["payment"] == "Наличные"]["total_sale"].sum()
            revenue_down = filtered_df[filtered_df["payment"] == "Рассрочка"]["down_payment"].sum()
            total_real_revenue = revenue_cash + revenue_down

            c1, c2 = st.columns(2)
            c1.metric("💰 Живая Выручка в кассу (Нал + Взносы)", f"{total_real_revenue:,.2f} сом")
            c2.metric("📈 Общая Чистая прибыль от сделок", f"{filtered_df['profit'].sum():,.2f} сом")

            st.markdown("### 🖨️ Печать и Экспорт")
            
            excel_df = filtered_df.copy()
            excel_df["В рассрочку (сом)"] = excel_df.apply(lambda r: float(r["credit_balance"]) if r["payment"] == "Рассрочка" else 0.0, axis=1)
            excel_df = excel_df.rename(columns={
                "date": "Дата и время",
                "name": "Наименование товара / Договор рассрочки",
                "qty": "Кол-во / Позиций",
                "total_sale": "Общая сумма (сом)",
                "down_payment": "Оплачено Нал/Взнос (сом)",
                "payment": "Тип оплаты"
            })
            
            cols_to_save = ["Дата и время", "Наименование товара / Договор рассрочки", "Кол-во / Позиций", "Общая сумма (сом)", "Оплачено Нал/Взнос (сом)", "В рассрочку (сом)", "Тип оплаты"]
            excel_df = excel_df[cols_to_save]
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                excel_df.to_excel(writer, index=False, sheet_name='Отчет по продажам')
            
            st.download_button(
                label="📥 Скачать этот отчёт в Excel (для печати)",
                data=buffer.getvalue(),
                file_name=f"Otchet_Prodaj_{start_date}_to_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

            st.markdown("---")
            st.subheader("📋 Детализация продаж на сайте")
            
            display_web_df = filtered_df.copy()
            display_web_df["Оплачено Нал"] = display_web_df.apply(lambda r: r["total_sale"] if r["payment"] == "Наличные" else r["down_payment"], axis=1)
            display_web_df["В рассрочку"] = display_web_df.apply(lambda r: r["credit_balance"] if r["payment"] == "Рассрочка" else 0.0, axis=1)
            
            st.dataframe(display_web_df[["date", "name", "qty", "total_sale", "Оплачено Нал", "В рассрочку", "payment"]], use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("📊 Аналитика по рассрочкам (за все время)")
            credits_data = supabase.table("credit_payments").select("amount_expected, amount_paid").execute()
            if credits_data.data:
                df_creds = pd.DataFrame(credits_data.data)
                total_expected = df_creds["amount_expected"].sum()
                total_paid = df_creds["amount_paid"].sum()
                total_remaining = total_expected - total_paid
                
                cr1, cr2, cr3 = st.columns(3)
                cr1.metric("💳 Общая сумма выданных рассрочек", f"{total_expected:,.2f} сом")
                cr2.metric("✅ Всего собрано денег по рассрочкам", f"{total_paid:,.2f} сом")
                cr3.metric("🔴 Сколько еще ДОЛЖНЫ клиенты", f"{total_remaining:,.2f} сом", delta=f"-{total_remaining:,.0f} сом", delta_color="inverse")
            else:
                st.info("Активных рассрочек в системе пока нет.")

            st.markdown("---")
            st.subheader("✏️ Редактировать или Отменить продажу из детализации")
            sales_options = {f"[{s['date']}] {s['name'].capitalize()} — {s['qty']}шт = {float(s['total_sale']):.0f} сом ({s['payment']})": idx for idx, s in enumerate(sales_all.data)}
            
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

            if "pending_edit_sale" in st.session_state and st.session_state.pending_edit_sale:
                pe = st.session_state.pending_edit_sale
                @st.dialog("📋 Подтверждение изменения продажи")
                def confirm_edit_dialog():
                    st.warning("Внимательно проверьте исправленные данные:")
                    st.markdown(f"### Новая сумма сделки: {pe['new_total']:.2f} сом ({pe['payment']})")
                    col_y, col_n = st.columns(2)
                    if col_y.button("✅ Да, сохранить изменения", type="primary", use_container_width=True):
                        qty_diff = pe["new_qty"] - pe["old_qty"]
                        exist_b = supabase.table("products").select("*").eq("name", pe["pure_name"]).eq("date", pe["batch_date"]).execute()
                        if exist_b.data:
                            new_stock = int(exist_b.data[0]["qty"]) - qty_diff
                            supabase.table("products").update({"qty": new_stock}).eq("id", exist_b.data[0]["id"]).execute()
                        
                        single_cost = pe["total_cost"] / pe["old_qty"]
                        new_cost = pe["new_qty"] * single_cost
                        
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

            if "show_sale_delete" in st.session_state and st.session_state.show_sale_delete:
                s_del = st.session_state.show_sale_delete
                @st.dialog("⚠️ Отмена и удаление продажи")
                def delete_sale_dialog():
                    st.error("Отменить эту сделку в Supabase?")
                    col_y, col_n = st.columns(2)
                    if col_y.button("🔥 Да, отменить", type="primary", use_container_width=True):
                        if s_del["pure_name"] != "рассрочка":
                            exist_b = supabase.table("products").select("*").eq("name", s_del["pure_name"]).eq("date", s_del["batch_date"]).execute()
                            if exist_b.data:
                                new_stock = int(exist_b.data[0]["qty"]) + int(s_del["qty"])
                                supabase.table("products").update({"qty": new_stock}).eq("id", exist_b.data[0]["id"]).execute()
                        
                        supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                        st.session_state.show_sale_delete = None
                        st.success("Удалено из облака!")
                        st.rerun()
                    if col_n.button("Назад", type="secondary", use_container_width=True):
                        st.session_state.show_sale_delete = None
                        st.rerun()
                delete_sale_dialog()

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
