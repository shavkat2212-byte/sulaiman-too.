import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    # 1. ЗАГРУЗКА ДАННЫХ ИЗ БАЗЫ (Твои проверенные запросы)
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance, day, name").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    payments_res = supabase.table("credit_payments").select("amount_paid, payment_date, client_id").execute()
    
    try: suppliers_res = supabase.table("supplier_payments").select("*").execute()
    except: suppliers_res = type('obj', (object,), {'data': []})

    clients_raw = supabase.table("clients").select("id, fio").execute()
    clients_dict = {c["id"]: c["fio"] for c in clients_raw.data} if clients_raw.data else {}

    # --- МАТЕМАТИКА ВЕРХНИХ КАРТОЧЕК ---
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    total_credit_collected = sum(float(p["amount_paid"] or 0) for p in payments_res.data)
    
    manual_cash_flow = 0.0
    if ops_res.data:
        for op in ops_res.data:
            val = op.get("amount") or op.get("Сумма") or list(op.values())[1]
            try: manual_cash_flow += float(val)
            except: pass

    total_suppliers_paid = sum(float(sup.get('amount') or 0) for sup in suppliers_res.data)
    current_cash_in_hand = full_cash_sales + manual_cash_flow - total_suppliers_paid
    
    # Верхние карточки
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", f"{credit_debts - total_credit_collected:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль", f"{sum(float(s['profit'] or 0) for s in sales_res.data):,.2f} сом")
    
    st.markdown("---")
    
    # ФОРМА ВНЕСЕНИЯ/ИЗЪЯТИЯ ДЕНЕГ
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
        comment = st.text_input("Комментарий / Причина")
        
        if st.form_submit_button("Выполнить операцию"):
            actual = amount if "Положить" in op_type else -amount
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"), 
                "amount": actual, 
                "comment": comment or op_type
            }).execute()
            st.success("Операция проведена!")
            st.rerun()

    # --- КАЛЕНДАРНЫЙ ФИЛЬТР ПЕРИОДА ДЛЯ ОБЕИХ ТАБЛИЦ ---
    st.markdown("---")
    st.subheader("🔍 Выберите период для просмотра приходов и расходов кассы")
    today_date = datetime.now().date()
    date_range = st.date_input("Диапазон дат истории кассы", value=(today_date, today_date))
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = today_date, today_date

    # --- СБОР И ОБЪЕДИНЕНИЕ ВСЕХ ДАННЫХ ДЛЯ ТАБЛИЦ ---
    income_records = []  # Список приходов
    expense_records = [] # Список расходов

    # 1. Добавляем прямые продажи за наличку из таблицы sales
    for s in sales_res.data:
        if s.get("payment") == "Наличные" and s.get("day"):
            try: d_obj = datetime.strptime(s["day"], "%Y-%m-%d").date()
            except: d_obj = today_date
            
            if start_date <= d_obj <= end_date:
                income_records.append({
                    "Дата": s["day"], 
                    "Сумма (сом)": int(s["total_sale"]), 
                    "Описание / Причина": f"Наличная продажа: {s.get('name', '')}"
                })

    # 2. Добавляем ручные операции и первоначальные взносы из cash_operations
    if ops_res.data:
        for op in ops_res.data:
            op_date = str(op.get('date') or op.get('Дата') or "")
            try: d_obj = datetime.strptime(op_date[:10], "%Y-%m-%d").date()
            except:
                try: d_obj = datetime.strptime(op_date[:10], "%d.%m.%Y").date()
                except: d_obj = today_date
                
            if start_date <= d_obj <= end_date:
                # Определяем сумму и комментарий динамически
                amt_val = op.get("amount") or op.get("Сумма") or list(op.values())[1]
                comm_val = op.get("comment") or op.get("Комментарий") or op.get("Комментарий / Причина") or "-"
                try:
                    amt = float(amt_val)
                    item = {"Дата": op_date, "Сумма (сом)": int(abs(amt)), "Описание / Причина": comm_val}
                    if amt > 0:
                        income_records.append(item)
                    else:
                        expense_records.append(item)
                except: pass

    # 3. Добавляем оплаты долей рассрочек от клиентов из credit_payments
    for p in payments_res.data:
        p_amt = float(p.get("amount_paid") or 0)
        p_date = p.get("payment_date") or ""
        if p_amt > 0 and p_date:
            try: d_obj = datetime.strptime(p_date[:10], "%d.%m.%Y").date()
            except: d_obj = today_date
            
            if start_date <= d_obj <= end_date:
                client_name = clients_dict.get(p.get("client_id"), "Клиент")
                income_records.append({
                    "Дата": p_date, 
                    "Сумма (сом)": int(p_amt), 
                    "Описание / Причина": f"Погашение доли рассрочки от {client_name}"
                })

    # 4. Добавляем выплаты контрагентам из supplier_payments
    for sup in suppliers_res.data:
        sup_date = sup.get("date") or ""
        try: d_obj = datetime.strptime(sup_date[:10], "%d.%m.%Y").date()
        except: d_obj = today_date
        
        if start_date <= d_obj <= end_date:
            expense_records.append({
                "Дата": sup_date, 
                "Сумма (сом)": int(float(sup.get('amount') or 0)), 
                "Описание / Причина": f"Выплата поставщику {sup.get('supplier')}: {sup.get('comment', '')}"
            })

    # --- ТАБЛИЦА 1: ВСЕ ПРИХОДЫ ---
    st.subheader("🟢 История кассовых приходов (Все наличные поступления)")
    if income_records:
        df_inc = pd.DataFrame(income_records).sort_values(by="Дата", ascending=False)
        st.dataframe(df_inc, use_container_width=True, hide_index=True)
        st.markdown(f"**💰 ИТОГО ВСЕХ ПРИХОДОВ ЗА ПЕРИОД: `{df_inc['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Приходов за указанный период нет.")

    st.markdown("---")

    # --- ТАБЛИЦА 2: ВСЕ РАСХОДЫ ---
    st.subheader("🔴 История расходов из кассы (Все выдачи и изъятия)")
    if expense_records:
        df_exp = pd.DataFrame(expense_records).sort_values(by="Дата", ascending=False)
        st.dataframe(df_exp, use_container_width=True, hide_index=True)
        st.markdown(f"**💸 ИТОГО ВСЕХ РАСХОДОВ ЗА ПЕРИОД: `{df_exp['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Расходов за указанный период нет.")
