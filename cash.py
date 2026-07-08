import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    # 1. Прямые наличные продажи
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    
    # 2. Долги клиентов по рассрочкам
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    
    # 3. Собранные платежи по рассрочкам
    paid_credits_res = supabase.table("credit_payments").select("amount_paid").execute()
    total_credit_collected = sum(float(p["amount_paid"]) for p in paid_credits_res.data)
    
    # 4. Все операции в кассе (включая первоначальные взносы от активных и удаленных продаж)
    manual_cash_flow = sum(float(op['amount']) for op in ops_res.data)
    
    # ИСПРАВЛЕННАЯ ФОРМУЛА: down_payments_cash убран, так как он уже сидит внутри manual_cash_flow
    current_cash_in_hand = full_cash_sales + manual_cash_flow
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", f"{credit_debts - total_credit_collected:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль", f"{sum(float(s['profit']) for s in sales_res.data):,.2f} сом")
    
    st.markdown("---")
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
        comment = st.text_input("Комментарий / Причина")
        
        if st.form_submit_button("Выполнить операцию"):
            actual = amount if "Положить" in op_type else -amount
            supabase.table("cash_operations").insert({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "amount": actual, "comment": comment or op_type}).execute()
            st.success("Операция проведена!")
            st.rerun()
