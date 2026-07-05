import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database import supabase

def show_sales_page():
    st.header("Оформить продажу (Корзина покупок)")
    stock_res = supabase.table("products").select("*").gt("qty", 0).execute()
    clients_res = supabase.table("clients").select("*").order("fio").execute()
    
    if not stock_res.data:
        st.warning("На складе нет доступных товаров для продажи")
        return

    col_form, col_cart = st.columns([1.2, 1])
    with col_form:
        st.subheader("🛒 Выбор товаров")
        unique_names = sorted(list(set(row["name"].capitalize() for row in stock_res.data)))
        sel_display = st.selectbox("🔍 Выберите товар", unique_names)
        p_key = sel_display.lower()
        
        batches_options = {f"Поступление от {datetime.strptime(row['date'], '%Y-%m-%d').strftime('%d.%M.%Y') if '-' in row['date'] else row['date']} (Остаток: {row['qty']} шт.)": row["id"] for row in stock_res.data if row["name"] == p_key}
        selected_batch_label = st.selectbox("📦 Выберите партию", list(batches_options.keys()))
        batch_id = batches_options[selected_batch_label]
        chosen_batch = supabase.table("products").select("*").eq("id", batch_id).execute().data[0]
        
        sqty = st.number_input("Количество для продажи", min_value=1, max_value=int(chosen_batch["qty"]), value=1)
        custom_price = st.number_input("💰 Цена за 1 шт, сом", min_value=0.0, value=float(chosen_batch['price']))
        
        st.caption(f"ℹ️ Закупочная цена (себестоимость): {int(chosen_batch['cost'])} сом")
        
        if st.button("➕ Добавить в чек", use_container_width=True):
            st.session_state.cart.append({
                "batch_id": batch_id, "name": sel_display, "batch_date": chosen_batch["date"],
                "qty": sqty, "price": custom_price, "total": sqty * custom_price, "cost": float(chosen_batch["cost"]), "pure_name": p_key
            })
            st.success(f"Товар добавлен в чек!")
            st.rerun()

    with col_cart:
        st.subheader("🧾 Текущий чек (Корзина)")
        if not st.session_state.cart:
            st.info("Чек пока пуст.")
            total_cart_sum = 0.0
        else:
            cart_df = pd.DataFrame(st.session_state.cart)
            cart_df["Закупка (1 шт)"] = cart_df["cost"].astype(int)
            st.dataframe(cart_df[["name", "qty", "price", "Закупка (1 шт)", "total"]], use_container_width=True, hide_index=True)
            total_cart_sum = cart_df["total"].sum()
            st.markdown(f"### 💵 Сумма по чеку: {total_cart_sum:,.2f} сом")
            if st.button("🗑️ Очистить чек"):
                st.session_state.cart = []
                st.rerun()

    if st.session_state.cart:
        st.markdown("---")
        st.subheader("💳 Параметры оплаты чека")
        sale_date = st.date_input("📅 Дата продажи", value=datetime.now().date())
        pay_method = st.radio("Способ оплаты", ["Наличные", "Рассрочка"], horizontal=True)
        
        down_payment = 0.0
        months = 1
        client_id = None
        sel_client_name = ""
        
        if pay_method == "Рассрочка":
            if not clients_res.data:
                st.error("❌ Сначала добавьте клиента в разделе «База клиентов».")
                return
            client_opts = {f"{c['fio']} ({c['phone']})": c for c in clients_res.data}
            sel_client_label = st.selectbox("👤 Выберите клиента", list(client_opts.keys()))
            client_id = client_opts[sel_client_label]["id"]
            sel_client_name = client_opts[sel_client_label]["fio"]
            
            c_r1, c_r2 = st.columns(2)
            down_payment = c_r1.number_input("💵 Первоначальный взнос, сом", min_value=0.0, max_value=float(total_cart_sum), value=0.0)
            months = c_r2.number_input("📅 Срок рассрочки (месяцев)", min_value=1, max_value=24, value=6)
            
            net_debt = total_cart_sum - down_payment
            default_markup = months * 3
            
            st.markdown("#### 🛠️ Корректировка условий рассрочки")
            col_m1, col_m2 = st.columns(2)
            custom_markup_percent = col_m1.number_input("Процент наценки (всего за срок), %", min_value=0.0, value=float(default_markup), step=1.0)
            
            calculated_with_markup = net_debt + (net_debt * (custom_markup_percent / 100))
            default_monthly = round(calculated_with_markup / months) if months > 0 else 0
            
            monthly_payment = col_m2.number_input("Ежемесячный платёж (можно округлить вручную), сом", min_value=0, value=int(default_monthly), step=10)
            
            total_with_markup = monthly_payment * months
            overpayment = total_with_markup - net_debt
            
            st.warning(f"📊 Расчёт: Чистый долг: {net_debt:,.0f} сом | Всего с наценкой: {total_with_markup:,.0f} сом | Переплата: {overpayment:,.0f} сом")
        else:
            total_with_markup = 0
            monthly_payment = 0

        if st.button("🚀 Оформить и провести сделку", type="primary", use_container_width=True):
            if pay_method == "Рассрочка" and not client_id:
                st.error("❌ Выберите клиента для рассрочки!")
                return
                
            base_group_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            day_str = sale_date.strftime("%Y-%m-%d")
            
            # ФОРМАТИРОВАНИЕ ДАТЫ: День.Месяц.Год ЧЧ:ММ
            formatted_date_full = f"{sale_date.strftime('%d.%m.%Y')} {datetime.now().strftime('%H:%M')}"
            # Уникальный читаемый номер договора из ДДММ и минут
            contract_num_suffix = datetime.now().strftime("%d%m-%H%M")
            
            try:
                total_cost_sum = 0.0
                items_list_str = []
                for item in st.session_state.cart:
                    p_res = supabase.table("products").select("qty").eq("id", item["batch_id"]).execute().data[0]
                    new_qty = int(p_res["qty"]) - item["qty"]
                    supabase.table("products").update({"qty": new_qty}).eq("id", item["batch_id"]).execute()
                    total_cost_sum += (item["qty"] * item["cost"])
                    items_list_str.append(f"{item['name']} ({item['qty']} шт.)")
                
                goods_summary = ", ".join(items_list_str)
                
                if pay_method == "Наличные":
                    for idx, item in enumerate(st.session_state.cart):
                        t_cost = item["qty"] * item["cost"]
                        unique_sale_id = f"{base_group_id}_{idx}"
                        
                        # Красивый перевод даты прихода товара для отображения
                        try:
                            b_date_formatted = datetime.strptime(item['batch_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
                        except:
                            b_date_formatted = item['batch_date']

                        supabase.table("sales").insert({
                            "id": unique_sale_id, "date": formatted_date_full, "day": day_str,
                            "name": f"{item['name']} (приход {b_date_formatted})", "pure_name": item["pure_name"], "batch_date": item["batch_date"],
                            "qty": item["qty"], "total_sale": int(item["total"]), "total_cost": int(t_cost), "profit": int(item["total"] - t_cost),
                            "payment": "Наличные", "down_payment": 0, "credit_balance": 0, "client_id": None
                        }).execute()
                else:
                    contract_name = f"Договор рассрочки №{contract_num_suffix} [{goods_summary}] — {sel_client_name}"
                    supabase.table("sales").insert({
                        "id": base_group_id, "date": formatted_date_full, "day": day_str,
                        "name": contract_name, "pure_name": "рассрочка", "batch_date": day_str,
                        "qty": 1, "total_sale": int(total_cart_sum), "total_cost": int(total_cost_sum), "profit": int(total_cart_sum - total_cost_sum),
                        "payment": "Рассрочка", "down_payment": int(down_payment), "credit_balance": int(total_with_markup), "client_id": client_id
                    }).execute()
                    
                    if down_payment > 0:
                        supabase.table("cash_operations").insert({
                            "date": formatted_date_full, 
                            "amount": float(down_payment), 
                            "comment": f"Перв. взнос по рассрочке №{contract_num_suffix} от {sel_client_name}"
                        }).execute()
                
                if pay_method == "Рассрочка" and client_id:
                    for m in range(1, months + 1):
                        due_date_obj = sale_date + timedelta(days=30 * m)
                        # Переводим плановую дату в красивый вид ДД.ММ.ГГГГ
                        formatted_due_date = due_date_obj.strftime("%d.%m.%Y")
                        try:
                            supabase.table("credit_payments").insert({
                                "sale_id": base_group_id, "client_id": client_id, "due_date": formatted_due_date,
                                "amount_expected": int(monthly_payment), "amount_paid": 0, "status": "Не оплачен"
                            }).execute()
                        except: continue
                            
                st.session_state.cart = []
                st.success("🎉 Сделка успешно проведена!")
                st.rerun()
            except Exception as e: st.error(f"Ошибка базы данных: {e}")
