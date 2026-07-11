# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия программы: 1.4 (Добавлен тип "Выплата за товар")

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    # 1. Прямые наличные продажи
    full_cash_sales = sum(float(s["total_sale"]) for s in sales_res.data if s.get("payment") == "Наличные")
    
    # 2. Все операции из cash_operations (взносы, погашения, расходы)
    manual_cash_flow = sum(float(op['amount']) for op in ops_res.data)
    
    current_cash_in_hand = full_cash_sales + manual_cash_flow

    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", 
              f"{sum(float(s.get('credit_balance', 0)) for s in sales_res.data if s.get('payment') == 'Рассрочка'):,} сом")
    c3.metric("📈 Чистая прибыль (всего)", 
              f"{sum(float(s.get('profit', 0)) for s in sales_res.data):,.2f} сом")

    st.markdown("---")
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")

    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", [
            "Положить деньги (Пополнение/Сдача)",
            "Взять деньги (Инкассация/Личные нужды)",
            "Выплата за товар (Поставщику)"
        ])
        
        amount = st.number_input("Сумма, сом", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий / Причина", 
                               value="Выплата поставщику" if "Выплата за товар" in op_type else "")
        
        if st.form_submit_button("Выполнить операцию", type="primary"):
            if "Положить" in op_type or "Выплата" not in op_type:
                actual = amount
            else:
                actual = -amount
                
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "amount": actual,
                "comment": comment or op_type
            }).execute()
            st.success("✅ Операция успешно проведена!")
            st.rerun()

    st.markdown("---")
    st.subheader("📜 История кассовых операций")
    if ops_res.data:
        df_ops = pd.DataFrame(ops_res.data)
        # Красивое отображение
        df_ops_display = df_ops.copy()
        df_ops_display["amount"] = df_ops_display["amount"].map('{:,.0f}'.format)
        st.dataframe(df_ops_display[["id", "date", "amount", "comment", "created_at"]], 
                     use_container_width=True, hide_index=True)
    else:
        st.info("История операций пуста.")
