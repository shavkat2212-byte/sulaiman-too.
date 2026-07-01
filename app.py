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
        c_id = client_opts
