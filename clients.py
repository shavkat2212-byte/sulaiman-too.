# Магазин «Сулайман-Тоо» — Модуль: Клиенты и рассрочки
# Версия программы: 1.3.1 (Полное исправление отображения архивных дат .00. на экране)

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_clients_page():
    st.title("👥 Управление клиентами и рассрочками")
    
    tab_manage, tab_installments_window = st.tabs(["🗂️ База и Редактирование", "💳 Окно контроля рассрочек"])
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
    # ВКЛАДКА 2: ИСПРАВЛЕННОЕ ОКНО КОНТРОЛЯ РАССЧЁТА ПРИБЫЛИ И ПЛАНОВЫХ ОТЧЁТОВ
    # =========================================================================
    with tab_installments_window:
        st.subheader("📋 Мониторинг договоров, Прибыли и Погашений")
        
        if not c_all.data:
            st.info("В базе данных ещё нет клиентов.")
        else:
            try:
                sales_res = supabase.table("sales").select("*").eq("payment", "Рассрочка").execute()
                all_sales = sales_res.data if sales_res.data else []
                payments_res = supabase.table("credit_payments").select("*").execute()
                all_payments = payments_res.data if payments_res.data else []
            except Exception as e:
                st.error(f"Ошибка Supabase: {e}")
                all_sales, all_payments = [], []

            st.markdown("### 📊 Аналитика активных договоров рассрочки")
            installments_summary = []
            
            for s in all_sales:
                client_fio = "Неизвестный клиент"
                for cl in c_all.data:
                    if cl["id"] == s["client_id"]:
                        client_fio = cl["fio"]
                        break
                
                sale_payments = [p for p in all_payments if p["sale_id"] == s["id"]]
                already_paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_payments)
                retail_with_markup = int(s.get("credit_balance", 0) or 0)
                current_debt_left = retail_with_markup - already_paid
                
                unpaid_payments = [p for p in sale_payments if p["status"] != "Оплачен"]
                
                def get_unpaid_sort(x):
                    p_d = str(x.get('due_date', ''))
                    # Если в базе лежит старая битая запись (05.00.2026), подменяем на реальный месяц
                    if ".00." in p_d: 
                        p_d = p_d.replace(".00.", f".{datetime.now().strftime('%m')}.")
                    try: return datetime.strptime(p_d, "%d.%m.%Y")
                    except: return datetime.now()

                unpaid_payments_sorted = sorted(unpaid_payments, key=get_unpaid_sort)
                monthly_payment_sum = int(unpaid_payments_sorted[0]["amount_expected"]) if unpaid_payments_sorted else 0
                
                cost_price = int(s.get("total_cost", 0) or 0)
                sale_price = int(s.get("total_sale", 0) or 0)
                down_pay = int(s.get("down_payment", 0) or 0)
                
                expected_profit = (down_pay + retail_with_markup) - cost_price

                if current_debt_left > 0:
                    installments_summary.append({
                        "Клиент": client_fio,
                        "Договор / Состав товаров": s["name"],
                        "Закупка (сом)": cost_price,
                        "Цена продажи (сом)": sale_price,
                        "Перв. взнос (сом)": down_pay,
                        "Долг + наценка (сом)": retail_with_markup,
                        "Остаток долга (сом)": int(current_debt_left),
                        "Ежемес. платёж (сом)": monthly_payment_sum,
                        "Чистая прибыль (сом)": expected_profit
                    })

            if not installments_summary:
                st.info("На данный момент нет активных рассрочек.")
            else:
                df_summary = pd.DataFrame(installments_summary)
                st.dataframe(
                    df_summary[["Клиент", "Договор / Состав товаров", "Закупка (сом)", "Цена продажи (сом)", "Перв. взнос (сом)", "Долг + наценка (сом)", "Остаток долга (сом)", "Ежемес. платёж (сом)", "Чистая прибыль (сом)"]], 
                    use_container_width=True, 
                    hide_index=True
                )

            st.write("---")
            st.markdown("### 📅 Аналитика движений по периодам дат")
            
            col_d1, col_d2 = st.columns(2)
            start_date = col_d1.date_input("🗓️ Начало периода", value=datetime.now().date())
            end_date = col_d2.date_input("🗓️ Конец периода", value=datetime.now().date())
            
            tab_fact, tab_plan = st.tabs(["💰 Фактически оплачено (Касса)", "⏳ Должны оплатить по плану"])
            
            with tab_fact:
                if st.button("🔍 Рассчитать фактические погашения", use_container_width=True):
                    try:
                        ops_res = supabase.table("cash_operations").select("*").execute()
                        if ops_res.data:
                            filtered_ops = []
                            total_period_income = 0.0
                            for op in ops_res.data:
                                if "Погашение рассрочки" in str(op.get("comment", "")) or "Перв. взнос" in str(op.get("comment", "")):
                                    op_date_str = op["date"]
                                    try:
                                        if "." in op_date_str[:10]:
                                            op_date = datetime.strptime(op_date_str[:10], "%d.%m.%Y").date()
                                        else:
                                            op_date = datetime.strptime(op_date_str[:10], "%Y-%m-%d").date()
                                            
                                        if start_date <= op_date <= end_date:
                                            filtered_ops.append({
                                                "Дата и время": op_date_str,
                                                "Сумма внесения (сом)": int(float(op["amount"])),
                                                "Комментарий": op["comment"]
                                            })
                                            total_period_income += float(op["amount"])
                                    except: continue
                            if filtered_ops:
                                st.success(f"Всего денег получено за период: **{int(total_period_income):,} сом**")
                                st.dataframe(pd.DataFrame(filtered_ops), use_container_width=True, hide_index=True)
                            else:
                                st.info("За выбранный период фактических платежей не найдено.")
                    except Exception as e: st.error(f"Ошибка кассового отчета: {e}")
            
            with tab_plan:
                if st.button("🗓️ Показать план ожидаемых оплат", use_container_width=True):
                    filtered_plan = []
                    total_expected_sum = 0
                    
                    # Получаем текущий текстовый номер месяца для подстраховки архивных строк
                    fallback_month = datetime.now().strftime("%m")
                    
                    for p in all_payments:
                        if p["status"] != "Оплачен":
                            try:
                                p_due_str = str(p["due_date"])
                                
                                # ИСПРАВЛЕНИЕ: Если в базе архивный баг с нулями, превращаем его на экране в текущий месяц
                                if ".00." in p_due_str:
                                    p_due_str = p_due_str.replace(".00.", f".{fallback_month}.")
                                    
                                if "." in p_due_str:
                                    due_date_obj = datetime.strptime(p_due_str, "%d.%m.%Y").date()
                                else:
                                    due_date_obj = datetime.strptime(p_due_str, "%Y-%m-%d").date()
                                    
                                if start_date <= due_date_obj <= end_date:
                                    cl_name = "Неизвестно"
                                    for cl in c_all.data:
                                        if cl["id"] == p["client_id"]:
                                            cl_name = cl["fio"]
                                            break
                                    to_pay = int(p["amount_expected"] - p["amount_paid"])
                                    filtered_plan.append({
                                        "Плановая дата платежа": due_date_obj.strftime("%d.%m.%Y"),
                                        "ФИО Клиента": cl_name,
                                        "Размер платежа (сом)": int(p["amount_expected"]),
                                        "Осталось доплатить (сом)": to_pay,
                                        "Статус": p["status"],
                                        "raw_date": due_date_obj
                                    })
                                    total_expected_sum += to_pay
                            except: continue
                            
                    if filtered_plan:
                        df_plan_res = pd.DataFrame(filtered_plan).sort_values("raw_date").drop(columns=["raw_date"])
                        st.warning(f"📉 Ожидаемый приток денег по плану на период: **{total_expected_sum:,} сом**")
                        st.dataframe(df_plan_res, use_container_width=True, hide_index=True)
                    else:
                        st.info("На выбранный период плановых платежей нет.")

            st.write("---")

            st.markdown("### 🔍 Карточка и индивидуальный график клиента")
            debtor_opts = {cl["fio"]: cl["id"] for cl in c_all.data}
            selected_debtor_fio = st.selectbox("Выберите ФИО клиента для детального просмотра:", ["-- Выберите ФИО --"] + list(debtor_opts.keys()), key="debtor_view_sb")
            
            if selected_debtor_fio != "-- Выберите ФИО --":
                chosen_client_id = debtor_opts[selected_debtor_fio]
                chosen_cl_sales = [s for s in all_sales if s["client_id"] == chosen_client_id]
                
                if chosen_cl_sales:
                    st.markdown(f"🛍️ **Список договоров клиента:** {selected_debtor_fio}")
                    details_list = []
                    for idx, s in enumerate(chosen_cl_sales):
                        details_list.append({
                            "№": idx + 1, "Дата": s["date"], "Договор": s["name"],
                            "Цена продажи (сом)": int(s.get("total_sale", 0)),
                            "Перв. взнос (сом)": int(s.get("down_payment", 0)),
                            "Долг + наценка (сом)": int(s.get("credit_balance", 0))
                        })
                    st.table(pd.DataFrame(details_list))
                    
                    st.markdown("#### 🗓️ Текущий календарный график платежей")
                    client_payments = [p for p in all_payments if p["client_id"] == chosen_client_id]
                    
                    if client_payments:
                        def get_date_sort(x):
                            p_d = str(x['due_date'])
                            if ".00." in p_d: 
                                p_d = p_d.replace(".00.", f".{datetime.now().strftime('%m')}.")
                            try: return datetime.strptime(p_d, "%d.%m.%Y")
                            except: return datetime.now()

                        for p_row in sorted(client_payments, key=get_date_sort):
                            display_due_date = str(p_row['due_date'])
                            if ".00." in display_due_date:
                                display_due_date = display_due_date.replace(".00.", f".{datetime.now().strftime('%m')}.")

                            col_p1, col_p2, col_p3, col_p4 = st.columns([2, 2, 2, 2])
                            col_p1.write(f"📅 Срок: {display_due_date}")
                            col_p2.write(f"💵 Ожидается: {int(p_row['amount_expected'])} сом")
                            col_p3.write(f"✅ Оплачено: {int(p_row['amount_paid'])} сом ({p_row['status']})")
                            
                            if p_row['status'] != 'Оплачен':
                                pay_amount = col_p4.number_input("Внести сумму", min_value=0.0, value=float(p_row['amount_expected'] - p_row['amount_paid']), key=f"win_pay_{p_row['id']}")
                                if col_p4.button("💳 Принять оплату", key=f"win_btn_{p_row['id']}", use_container_width=True):
                                    new_paid = float(p_row['amount_paid']) + pay_amount
                                    new_status = "Оплачен" if new_paid >= float(p_row['amount_expected']) else "Частично"
                                    
                                    now_formatted = datetime.now().strftime("%d.%m.%Y %H:%M")
                                    
                                    supabase.table("credit_payments").update({"amount_paid": new_paid, "status": new_status}).eq("id", p_row['id']).execute()
                                    supabase.table("cash_operations").insert({
                                        "date": now_formatted, 
                                        "amount": pay_amount, "comment": f"Погашение рассрочки от {selected_debtor_fio}"
                                    }).execute()
                                    st.success("Оплата зафиксирована!")
                                    st.rerun()
                    else:
                        st.info("Календарный график для этого клиента отсутствует.")
            # ===== ГЕНЕРАЦИЯ ДОГОВОРА =====
st.markdown("---")
st.subheader("📄 Сформировать договор")

if chosen_cl_sales:
    # Выбираем договор для печати
    sale_options = {
        f"{s['date']} | {s['name'][:50]} | {int(s.get('total_sale', 0)):,} сом": s
        for s in chosen_cl_sales
    }
    selected_sale_label = st.selectbox(
        "Выберите договор для печати",
        list(sale_options.keys()),
        key="contract_sale_select"
    )
    selected_sale = sale_options[selected_sale_label]

    # Данные клиента
    client_data = next((c for c in c_all.data if c["id"] == chosen_client_id), {})

    # Количество месяцев (пробуем взять из платежей)
    client_payments = [p for p in all_payments if p.get("sale_id") == selected_sale["id"]]
    months_count = len(client_payments) if client_payments else 6

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📄 Скачать договор (Word)", type="primary", use_container_width=True):
            try:
                from contract_generator import fill_contract, generate_payment_schedule
                import os

                template_path = "contract_template.docx"
                if not os.path.exists(template_path):
                    st.error("Файл шаблона contract_template.docx не найден!")
                else:
                    # Номер договора — используем ID продажи
                    contract_num = str(selected_sale.get("id", "б/н"))
                    contract_date = datetime.now().strftime("%d.%m.%Y")

                    total = float(selected_sale.get("total_sale", 0) or 0)
                    down = float(selected_sale.get("down_payment", 0) or 0)
                    product_name = selected_sale.get("name", "Товар")

                    schedule = generate_payment_schedule(total, down, months_count)

                    doc_bytes = fill_contract(
                        template_path=template_path,
                        contract_number=contract_num,
                        contract_date=contract_date,
                        client_name=client_data.get("fio", ""),
                        client_address=client_data.get("address", ""),
                        client_passport=client_data.get("passport", ""),
                        total_amount=total,
                        months=months_count,
                        product_name=product_name,
                        product_qty=int(selected_sale.get("qty", 1) or 1),
                        product_price=total,
                        down_payment=down,
                        schedule=schedule,
                    )

                    st.download_button(
                        label="⬇️ Нажмите, чтобы скачать договор",
                        data=doc_bytes,
                        file_name=f"Dogovor_{contract_num}_{client_data.get('fio', 'client')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
                    st.success("Договор сформирован!")
            except Exception as e:
                st.error(f"Ошибка при создании договора: {e}")
