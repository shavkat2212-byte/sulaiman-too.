import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    # 1. ЗАГРУЗКА ДАННЫХ ИЗ БАЗЫ (Твои оригинальные работающие запросы)
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance, day, name").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    payments_res = supabase.table("credit_payments").select("amount_paid, payment_date, client_id").execute()
    
    clients_raw = supabase.table("clients").select("id, fio").execute()
    clients_dict = {c["id"]: c["fio"] for c in clients_raw.data} if clients_raw.data else {}

    # --- МАТЕМАТИКА ВЕРХНИХ КАРТОЧЕК (Твой оригинал) ---
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    down_payments_cash = sum(float(s.get("down_payment", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    
    total_credit_collected = sum(float(p["amount_paid"]) for p in payments_res.data)
    manual_cash_flow = sum(float(op['amount']) for op in ops_res.data)
    
    # Твоя формула (Взносы пока тут, чтобы сошелся твой привычный баланс)
    current_cash_in_hand = full_cash_sales + down_payments_cash + manual_cash_flow
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", f"{credit_debts - total_credit_collected:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль", f"{sum(float(s['profit']) for s in sales_res.data):,.2f} сом")
    
    st.markdown("---")
    
    # ТВОЯ РОДНАЯ ФОРМА ВНЕСЕНИЯ/ИЗЪЯТИЯ
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

    # --- ДВУХКАЛЕНДАРНЫЙ ФИЛЬТР (БЕЗОПАСНЫЙ ВАРИАНТ) ---
    st.markdown("---")
    st.subheader("🔍 Выберите период просмотра кассовых приходов и расходов")
    col_d1, col_d2 = st.columns(2)
    start_date = col_d1.date_input("С даты", value=datetime.now().date(), key="cash_start")
    end_date = col_d2.date_input("По дату", value=datetime.now().date(), key="cash_end")

    st.markdown("---")

    # --- ТАБЛИЦА ПРИХОДОВ ЗА ПЕРИОД ---
    st.subheader("🟢 История кассовых приходов")
    
    inc_records = []
    # 1. Собираем наличные продажи
    for s in sales_res.data:
        if s.get("payment") == "Наличные" and s.get("day"):
            try: d_obj = datetime.strptime(s["day"], "%Y-%m-%d").date()
            except: continue
            if start_date <= d_obj <= end_date:
                inc_records.append({"Дата": s["day"], "Сумма (сом)": int(s["total_sale"]), "Описание": f"Наличная продажа: {s.get('name', '')}"})
                
    # 2. Собираем ручные приходы из cash_operations
    for op in ops_res.data:
        if float(op.get('amount', 0)) > 0 and op.get('date'):
            try: d_obj = datetime.strptime(op['date'][:10], "%Y-%m-%d").date()
            except: continue
            if start_date <= d_obj <= end_date:
                inc_records.append({"Дата": op['date'], "Сумма (сом)": int(op['amount']), "Описание": op.get('comment', 'Приход')})

    # 3. Собираем оплаты рассрочек
    for p in payments_res.data:
        p_amt = float(p.get("amount_paid", 0))
        if p_amt > 0 and p.get('payment_date'):
            try: d_obj = datetime.strptime(p['payment_date'][:10], "%d.%m.%Y").date()
            except: continue
            if start_date <= d_obj <= end_date:
                c_name = clients_dict.get(p.get("client_id"), "Клиент")
                inc_records.append({"Дата": p['payment_date'], "Сумма (сом)": int(p_amt), "Описание": f"Погашение рассрочки от {c_name}"})

    if inc_records:
        df_inc = pd.DataFrame(inc_records).sort_values(by="Дата", ascending=False)
        st.dataframe(df_inc, use_container_width=True, hide_index=True)
        st.markdown(f"**💰 ИТОГО ПРИХОДОВ ЗА ПЕРИОД: `{df_inc['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Приходов за этот период нет.")

    st.markdown("---")

    # --- ТАБЛИЦА РАСХОДОВ ЗА ПЕРИОД ---
    st.subheader("🔴 История расходов из кассы")
    
    exp_records = []
    # Собираем ручные расходы (всё что меньше 0) из cash_operations
    for op in ops_res.data:
        if float(op.get('amount', 0)) < 0 and op.get('date'):
            try: d_obj = datetime.strptime(op['date'][:10], "%Y-%m-%d").date()
            except: continue
            if start_date <= d_obj <= end_date:
                exp_records.append({"Дата": op['date'], "Сумма (сом)": int(abs(op['amount'])), "Описание": op.get('comment', 'Расход')})

    if exp_records:
        df_exp = pd.DataFrame(exp_records).sort_values(by="Дата", ascending=False)
        st.dataframe(df_exp, use_container_width=True, hide_index=True)
        st.markdown(f"**💸 ИТОГО РАСХОДОВ ЗА ПЕРИОД: `{df_exp['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Расходов за этот период нет.")
