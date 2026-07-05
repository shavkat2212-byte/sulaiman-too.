import streamlit as st
from database import supabase

def render_sales_page():
    st.title(" Магазин «Сулайман-Тоо» — Учет и Рассрочки")
    st.header("Оформить продажу (Корзина покупок)")

    # Инициализация корзины в сессии, если её нет
    if "cart" not in st.session_state:
        st.session_state.cart = []

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🛒 Выбор товаров")
        
        # 1. Загрузка товаров
        try:
            products_res = supabase.table("products").select("id, name").execute()
            products = products_res.data
        except Exception as e:
            st.error(f"Ошибка загрузки товаров: {e}")
            products = []

        if products:
            product_options = {p["name"]: p["id"] for p in products}
            selected_product_name = st.selectbox("Выберите товар", list(product_options.keys()))
            selected_product_id = product_options[selected_product_name]
            
            # 2. Загрузка партий для выбранного товара (включая закупочную цену)
            try:
                batches_res = supabase.table("batches").select("id, batch_date, stock_quantity, purchase_price").eq("product_id", selected_product_id).gt("stock_quantity", 0).execute()
                batches = batches_res.data
            except Exception as e:
                st.error(f"Ошибка загрузки партий: {e}")
                batches = []

            if batches:
                # Формируем список партий для selectbox
                batch_options = {f"Поступление от {b['batch_date']} (Остаток: {int(b['stock_quantity'])} шт.)": b for b in batches}
                selected_batch_label = st.selectbox("Выберите партию", list(batch_options.keys()))
                selected_batch_data = batch_options[selected_batch_label]
                
                # Закупочная цена из партии (принудительно в int)
                purchase_price = int(selected_batch_data.get("purchase_price", 0))
                
                # Поля ввода для количества и цены продажи
                quantity = st.number_input("Количество для продажи", min_value=1, max_value=int(selected_batch_data["stock_quantity"]), value=1, step=1)
                selling_price = st.number_input("Цена за 1 шт, сом", min_value=0, value=0, step=100)
                
                # Отображаем закупочную цену для информации (чтобы менеджер видел маржу)
                st.caption(f"ℹ️ Закупочная цена этой партии: {purchase_price} сом")

                if st.button("➕ Добавить в чек"):
                    # Добавляем товар в корзину с сохранением закупочной цены
                    item = {
                        "product_id": selected_product_id,
                        "product_name": selected_product_name,
                        "batch_id": selected_batch_data["id"],
                        "quantity": int(quantity),
                        "selling_price": int(selling_price),
                        "purchase_price": purchase_price  # <--- Сохраняем закупочную цену товара
                    }
                    st.session_state.cart.append(item)
                    st.toast(f"Добавлено: {selected_product_name}")
                    st.rerun()
            else:
                st.warning("Нет доступных партий с остатками для этого товара.")
        else:
            st.info("В базе данных ещё нет товаров.")

    with col2:
        st.markdown("### 📋 Текущий чек (Корзина)")
        
        if not st.session_state.cart:
            st.info("Чек пока пуст.")
        else:
            total_sum = 0
            cart_table = []
            
            for idx, item in enumerate(st.session_state.cart):
                subtotal = item["quantity"] * item["selling_price"]
                total_sum += subtotal
                cart_table.append({
                    "№": idx + 1,
                    "Товар": item["product_name"],
                    "Кол-во": item["quantity"],
                    "Цена (сом)": item["selling_price"],
                    "Закупка (сом)": item["purchase_price"],  # <-- Выводим в таблицу чека
                    "Итого": subtotal
                })
            
            st.dataframe(cart_table, use_container_width=True, hide_index=True)
            st.markdown(f"#### Всего к оплате: **{total_sum} сом**")
            
            if st.button("🗑️ Очистить корзину"):
                st.session_state.cart = []
                st.rerun()
                
            st.write("---")
            st.markdown("### 💳 Завершение операции")
            
            # Выбор клиента для оформления рассрочки или обычной продажи
            try:
                clients_res = supabase.table("clients").select("id, full_name").execute()
                clients = clients_res.data
            except Exception as e:
                st.error(f"Ошибка загрузки клиентов: {e}")
                clients = []

            client_options = {"Обычный покупатель (Наличные)": None}
            for cl in clients:
                client_options[cl["full_name"]] = cl["id"]
                
            selected_client_name = st.selectbox("Выберите покупателя (для Рассрочки обязательно)", list(client_options.keys()))
            client_id = client_options[selected_client_name]
            
            is_installment = st.checkbox("Оформить как договор рассрочки")
            
            if is_installment and not client_id:
                st.warning("⚠️ Для оформления рассрочки необходимо выбрать клиента из базы!")
                
            if st.button("🚀 Подтвердить и провести продажу"):
                if is_installment and not client_id:
                    st.error(" Невозможно оформить рассрочку без привязки к клиенту.")
                    return
                
                try:
                    # Формируем название Договора из состава товаров для рассрочки
                    items_summary = ", ".join([f"{i['product_name']} x{i['quantity']}" for i in st.session_state.cart])
                    contract_name = f"Договор рассрочки: {items_summary}" if is_installment else f"Продажа: {items_summary}"
                    
                    # 1. Записываем каждую позицию из корзины в таблицу продаж
                    for item in st.session_state.cart:
                        sale_data = {
                            "client_id": client_id,
                            "product_id": item["product_id"],
                            "batch_id": item["batch_id"],
                            "quantity": item["quantity"],
                            "selling_price": item["selling_price"],
                            "purchase_price": item["purchase_price"],  # <--- Отправляем закупочную цену в Supabase
                            "contract_name": contract_name,
                            "total_amount": item["quantity"] * item["selling_price"],
                            "is_installment": is_installment
                        }
                        supabase.table("sales").insert(sale_data).execute()
                        
                        # 2. Обновляем остатки на складе (в таблице партий batches)
                        # Сначала считываем текущий остаток
                        current_batch = supabase.table("batches").select("stock_quantity").eq("id", item["batch_id"]).single().execute().data
                        new_qty = int(current_batch["stock_quantity"]) - item["quantity"]
                        supabase.table("batches").update({"stock_quantity": new_qty}).eq("id", item["batch_id"]).execute()
                    
                    # 3. Если это рассрочка, обновляем долг клиента в таблице клиентов
                    if is_installment:
                        current_client = supabase.table("clients").select("total_debt").eq("id", client_id).single().execute().data
                        new_debt = int(current_client.get("total_debt", 0) or 0) + total_sum
                        supabase.table("clients").update({"total_debt": new_debt}).eq("id", client_id).execute()
                    
                    # 4. Если это наличные, фиксируем поступление в кассу
                    if not is_installment:
                        # (Здесь твоя стандартная логика добавления операции в cash.py / cash table)
                        pass
                        
                    st.success("🎉 Продажа успешно проведена! Остатки списаны.")
                    st.session_state.cart = []
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Ошибка при проведении операции: {e}")
