# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия программы: 1.5 (Добавлены итоги, фильтр по датам и экспорт в Excel)

import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    # Основные метрики
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    full_cash_sales = sum(float(s["total_sale"]) for s in sales_res.data if s.get("payment") == "Наличные")
    manual_cash_flow = sum(float(op['amount']) for op in ops_res.data)
    current_cash_in_hand = full_cash_sales + manual_cash_flow

    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", 
              f"{sum(float(s.get('credit_balance', 0)) for s in sales_res.data if s.get('payment') == 'Рассрочка'):,} сом")
    c3.metric("📈 Чистая прибыль (всего)", 
              f"{sum(float(s.get('profit', 0)) for s in sales_res.data):,.2f} сом")

    st.markdown("---")
    st.subheader("📜 История кассовых операций")

    # Фильтр по датам
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        start_date = st.date_input("Начало периода", value=datetime.now().date() - timedelta(days=30))
    with col_f2:
        end_date = st.date_input("Конец периода", value=datetime.now().date())

    # Фильтрация операций
    df_ops = pd.DataFrame(ops_res.data) if ops_res.data else pd.DataFrame()
    
    if not df_ops.empty:
        df_ops['date_obj'] = pd.to_datetime(df_ops['date'].str[:10], errors='coerce').dt.date
        filtered_ops = df_ops[(df_ops['date_obj'] >= start_date) & (df_ops['date_obj'] <= end_date)]
    else:
        filtered_ops = pd.DataFrame()

    # Итоги по отфильтрованным операциям
    total_in = filtered_ops[filtered_ops['amount'] > 0]['amount'].sum() if not filtered_ops.empty else 0
    total_out = abs(filtered_ops[filtered_ops['amount'] < 0]['amount'].sum()) if not filtered_ops.empty else 0
    net = total_in - total_out

    # ==================== ЭКСПОРТ В EXCEL ====================
    if not filtered_ops.empty:
        col_exp1, col_exp2 = st.columns([5, 2])
        with col_exp2:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                filtered_ops[["id", "date", "amount", "comment", "created_at"]].to_excel(
                    writer, index=False, sheet_name="Касса"
                )
            excel_buffer.seek(0)

            st.download_button(
                label="📥 Экспорт в Excel",
                data=excel_buffer,
                file_name=f"Касса_{start_date}_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    # =====================================================================

    # Таблица
    if not filtered_ops.empty:
        display_df = filtered_ops[["id", "date", "amount", "comment", "created_at"]].copy()
        display_df["amount"] = display_df["amount"].map('{:,.0f}'.format)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Операций за выбранный период нет.")

    # ==================== ИТОГИ ====================
    st.markdown("---")
    st.subheader("📊 Итоги по периоду")
    col_sum1, col_sum2, col_sum3 = st.columns(3)
    col_sum1.metric("💰 Пополнения в кассу", f"{total_in:,.0f} сом", delta=None)
    col_sum2.metric("📤 Расходы / Изъятия", f"{total_out:,.0f} сом", delta=None)
    col_sum3.metric("📈 Чистый результат", f"{net:,.0f} сом", 
                   delta="Положительный" if net >= 0 else "Отрицательный")
    # =====================================================================

    st.markdown("---")
    st.subheader("📥 / 📤 Новая операция")

    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", [
            "Положить деньги (Пополнение/Сдача)",
            "Взять деньги (Инкассация/Личные нужды)",
            "Выплата за товар (Поставщику)"
        ])
        
        amount = st.number_input("Сумма, сом", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий / Причина", 
                               value="Выплата поставщику" if "Выплата" in op_type else "")
        
        if st.form_submit_button("Выполнить операцию", type="primary"):
            actual = amount if "Положить" in op_type or "Выплата" not in op_type else -amount
            
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "amount": actual,
                "comment": comment or op_type
            }).execute()
            st.success("✅ Операция успешно проведена!")
            st.rerun()
