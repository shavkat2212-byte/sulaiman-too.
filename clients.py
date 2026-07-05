import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_clients_page():
    st.title("👥 Управление клиентами и рассрочками")
    
    # Создаем две удобные вкладки
    tab_manage, tab_installments_window = st.tabs(["🗂️ База и Редактирование", "💳 Окно контроля рассрочек"])
    
    # Сразу загружаем всех клиентов из базы данных
    c_all = supabase.table("clients").select("*").order("fio").execute()

    # =========================================================================
    # ВКЛАДКА 1: УПРАВЛЕНИЕ БАЗОЙ КЛИЕНТОВ И РЕДАКТИРОВАНИЕ
    # =========================================================================
    with tab_manage:
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
                        st.success("Клиент успешно добавлен!")
                        st.rerun()
                        
        with col_c2:
            st.subheader("✏️ Редактировать данные клиента")
            if c_all.data:
                client_edit_opts = {c["fio"]: c for c in c_all.data}
                selected_edit_name = st.selectbox("Выберите клиента для изменения", list(client_edit_opts.keys()))
                client_to_update = client_edit_opts[selected_edit_name]
                
                with st.form("client_edit_form"):
                    new_fio = st.text_input("Изменить ФИО", value=str(client_to_update["fio"]))
                    new_phone = st.text_input("Изменить телефон", value=str(client_to_update["phone"] or ""))
                    new_address = st.text_input("Изменить адрес", value=str(client_to_update.get("address") or ""))
                    new_passport = st.text_area("Изменить паспортные данные", value=str(client_to_update["passport"] or ""))
                    
                    if st.form_submit_button("💾 Сохранить изменения"):
                        supabase.table("clients").update({
                            "fio": new_fio.strip(), "phone": new_phone.strip() if new_phone.strip() else None,
                            "address": new_address.strip() if new_address.strip() else None, "passport": new_passport.strip() if new_passport.strip() else None
                        }).eq("id", client_to_update["id"]).execute()
                        st.success("Данные успешно обновлены!")
                        st.rerun()

        st.markdown("---")
        st.subheader("📋 Список всех клиентов в базе")
        if c_all.data:
            df_c = pd.DataFrame(c_all.data).drop(columns=["created_at"], errors="ignore")
            df_c = df_c.rename(columns={"id": "ID", "fio": "ФИО Клиента", "phone": "Телефон", "address": "Адрес проживания", "passport": "Паспортные данные"})
            st.dataframe(df_c[["ID", "ФИО Клиента", "Телефон", "Адрес проживания", "Паспортные данные"]], use_container_width=True, hide_index=True)

    # =========================================================================
    # ВКЛАДКА 2: ПОЛНОЦЕННОЕ ОКНО КОНТРОЛЯ РАССРОЧЕК И АНАЛИТИКИ ПРИБЫЛИ
    # =========================================================================
    with tab_installments_window:
        st.subheader("📋 Мониторинг договоров, Прибыли и Погашений")
        
        if not c_all.data:
            st.info("В базе данных ещё нет клиентов.")
        else:
            try:
                # Загружаем договора рассрочки
                sales_res = supabase.table("sales").select("*").eq("payment", "Рассрочка").execute()
                all_sales = sales_res.data if sales_res.data else []
                
                # Загружаем плановые платежи
                payments_res = supabase.table("credit_payments").select("*").execute()
                all_payments = payments_res.data if payments_res.data else []
            except Exception as e:
                st.error(f"Ошибка загрузки данных из Supabase: {e}")
                all_sales, all_payments = [], []

            # -----------------------------------------------------------------
            # 1. ГЛАВНЫЙ ОТЧЕТ: СПИСОК ДОГОВОРОВ С РАСЧЕТОМ СЕБЕСТОИМОСТИ И ПРИБЫЛИ
            # -----------------------------------------------------------------
            st.markdown("### 📊 Аналитика активных договоров рассрочки")
            
            installments_summary = []
            
            for s in all_sales:
                # Ищем ФИО клиента по его client_id
                client_fio = "Неизвестный клиент"
                for cl in c_all.data:
                    if cl["id"] == s["client_id"]:
                        client_fio = cl["fio"]
                        break
                
                # Получаем плановые платежи по данному конкретному договору (sale_id)
                sale_payments = [p for p in all_payments if p["sale_id"] == s["id"]]
                
                # Считаем, сколько клиент уже выплатил по этому договору
                already_paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_payments)
                
                # Остаток долга = Полная сумма с наценкой (credit_balance) минус то, что уже оплачено
                current_debt_left = int(s.get("credit_balance", 0)) - already_paid
                
                # Ближайший ежемесячный платеж (первый неоплаченный)
                unpaid_payments = [p for p in sale_payments if p["status"] != "Оплачен"]
                monthly_payment_sum = int(unpaid_payments[0]["amount_expected"]) if unpaid_payments else 0
                
                # Себестоимость закупки партии (total_cost) и розничная цена (total_sale)
                cost_price = int(s.get("total_cost", 0) or 0)
                retail_price = int(s.get("credit_balance", 0) or 0) # полная стоимость к возврату с наценкой
                
                # Ожидаемая чистая прибыль с договора = Сколько должен вернуть всего - Сколько стоил в закупе
                expected_profit = retail_price - cost_price

                # Выводим только активные договора (где остаток долга больше нуля)
                if current_debt_left > 0:
                    installments_summary.append({
                        "Клиент": client_fio,
                        "Договор / Состав товаров": s["name"],
                        "Закупка (сом)": cost_price,
                        "Сумма с наценкой (сом)": retail_price,
                        "Остаток долга (сом)": int(current_debt_left),
                        "Ежемес. платёж (сом)": monthly_payment_sum,
                        "Ожидаемая прибыль (сом)": expected_profit,
                        "sale_id": s["id"],
                        "client_id": s["client_id"]
                    })

            if not installments_summary:
                st.info("На данный момент нет активных задолженностей по рассрочкам.")
            else:
                df_summary = pd.DataFrame(installments_summary)
                
                # Отображаем красивую аналитическую таблицу
                st.dataframe(
                    df_summary[["Клиент", "Договор / Состав товаров", "Закупка (сом)", "Сумма с наценкой (сом)", "Остаток долга (сом)", "Ежемес. платёж (сом)", "Ожидаемая прибыль (сом)"]], 
                    use_container_width=True, 
                    hide_index=True
                )
                
                # Краткие итоги по всему портфелю рассрочек
                st.markdown(f"""
                💡 **Итого по активной рассрочке:** Всего в закупе на сумму **{df_summary['Закупка (сом)'].sum():,} сом**. 
                Остаток чистой задолженности клиентов: **{df_summary['Остаток долга (сом)'].sum():,} сом**. 
                Прогнозируемая чистая прибыль после полного погашения: **{df_summary['Ожидаемая прибыль (сом)'].sum():,} сом**.
                """)

            st.write("---")
            
            # -----------------------------------------------------------------
            # 2. ФИЛЬТР ПО ПЕРИОДУ: ПОСМОТРЕТЬ ФАКТИЧЕСКИЕ ПОГАШЕНИЯ ЗА ВРЕМЯ
            # -----------------------------------------------------------------
            st.markdown("### 📅 Отчёт по фактическим погашениям за период")
            
            col_d1, col_d2 = st.columns(2)
            start_date = col_d1.date_input("🗓️ Начало периода", value=datetime.now().date())
            end_date = col_d2.date_input("🗓️ Конец периода", value=datetime.now().date())
            
            if st.button("🔍 Показать погашения за период", type="secondary", use_container_width=True):
                try:
                    # Ищем операции погашения в кассе по комментарию "Погашение рассрочки"
                    ops_res = supabase.table("cash_operations").select("*").execute()
                    
                    if ops_res.data:
                        filtered_ops = []
                        total_period_income = 0.0
                        
                        for op in ops_res.data:
                            # Проверяем, что операция относится к рассрочке
                            if "Погашение рассрочки" in str(op.get("comment", "")):
                                # Вытаскиваем дату операции YYYY-MM-DD
                                op_date_str = op["date"][:10]
                                try:
                                    op_date = datetime.strptime(op_date_str, "%Y-%m-%d").date()
                                    if start_date <= op_date <= end_date:
                                        filtered_ops.append({
                                            "Дата и время": op["date"],
                                            "Сумма внесения (сом)": int(float(op["amount"])),
                                            "Комментарий / Кто оплатил": op["comment"]
                                        })
                                        total_period_income += float(op["amount"])
                                except: continue
                                
                        if filtered_ops:
                            st.success(f"💰 Всего за указанный период клиенты внесли: **{int(total_period_income):,} сом**")
                            st.dataframe(pd.DataFrame(filtered_ops), use_container_width=True, hide_index=True)
                        else:
                            st.info("За выбранный период платежей по погашению рассрочек не обнаружено.")
                except Exception as e:
                    st.error(f"Ошибка формирования отчета по периодам: {e}")

            st.write("---")

            # -----------------------------------------------------------------
            # 3. ДЕТАЛИЗАЦИЯ И ИНДИВИДУАЛЬНЫЙ ГРАФИК ВЫБРАННОГО КЛИЕНТА
            # -----------------------------------------------------------------
            st.markdown("### 🔍 Карточка и индивидуальный график клиента")
            
            debtor_opts = {cl["fio"]: cl["id"] for cl in c_all.data}
            selected_debtor_fio = st.selectbox("Выберите ФИО клиента для детального просмотра:", ["-- Выберите ФИО --"] + list(debtor_opts.keys()), key="debtor_view_sb")
            
            if selected_debtor_fio != "-- Выберите ФИО --":
                chosen_client_id = debtor_opts[selected_debtor_fio]
                
                # Фильтруем договора именно этого клиента
                chosen_cl_sales = [s for s in all_sales if s["client_id"] == chosen_client_id]
                
                if chosen_cl_sales:
                    st.markdown(f"🛍️ **Список оформленных договоров для:** {selected_debtor_fio}")
                    details_list = []
                    for idx, s in enumerate(chosen_cl_sales):
                        details_list.append({
                            "№": idx + 1,
                            "Дата оформления": s["date"][:10] if s.get("date") else "-",
                            "Название договора": s["name"],
                            "Полная сумма (сом)": int(s.get("credit_balance", 0))
                        })
                    st.table(pd.DataFrame(details_list))
                    
                    # Сразу выводим его календарный график платежей и форму приема оплаты
                    st.markdown("#### 🗓️ Текущий календарный график платежей")
                    client_payments = [p for p in all_payments if p["client_id"] == chosen_client_id]
                    
                    if client_payments:
                        for p_row in sorted(client_payments, key=lambda x: x['due_date']):
                            col_p1, col_p2, col_p3, col_p4 = st.columns([2, 2, 2, 2])
                            col_p1.write(f"📅 Срок: {p_row['due_date']}")
                            col_p2.write(f"💵 Ожидается: {int(p_row['amount_expected'])} сом")
                            col_p3.write(f"✅ Оплачено: {int(p_row['amount_paid'])} сом ({p_row['status']})")
                            
                            if p_row['status'] != 'Оплачен':
                                pay_amount = col_p4.number_input("Внести сумму", min_value=0.0, value=float(p_row['amount_expected'] - p_row['amount_paid']), key=f"win_pay_{p_row['id']}")
                                if col_p4.button("💳 Принять оплату", key=f"win_btn_{p_row['id']}", use_container_width=True):
                                    new_paid = float(p_row['amount_paid']) + pay_amount
                                    new_status = "Оплачен" if new_paid >= float(p_row['amount_expected']) else "Частично"
                                    
                                    # Обновляем статус платежа
                                    supabase.table("credit_payments").update({"amount_paid": new_paid, "status": new_status}).eq("id", p_row['id']).execute()
                                    # Фиксируем приход денег в кассу
                                    supabase.table("cash_operations").insert({
                                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"), 
                                        "amount": pay_amount, 
                                        "comment": f"Погашение рассрочки от {selected_debtor_fio}"
                                    }).execute()
                                    
                                    st.success("Оплата успешно зафиксирована!")
                                    st.rerun()
                    else:
                        st.info("Календарный график для этого клиента отсутствует.")
                else:
                    st.warning("У этого клиента нет активных или прошлых договоров рассрочки.")
