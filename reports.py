import streamlit as st
import pandas as pd
import io
from datetime import datetime
from database import supabase

def show_reports_page():
    st.header("📊 Аналитика и история продаж")
    sales_all = supabase.table("sales").select("*").execute()
    
    if not sales_all.data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_all.data)
    df['day'] = pd.to_datetime(df['day']).dt.date
    st.subheader("🔍 Выберите период")
    date_range = st.date_input("Диапазон дат", value=(df['day'].min(), df['day'].max()))
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = df[(df['day'] >= start_date) & (df['day'] <= end_date)]
    else: filtered_df = df
        
    if not filtered_df.empty:
        revenue_cash = filtered_df[filtered_df["payment"] == "Наличные"]["total_sale"].sum()
        revenue_down = filtered_df[filtered_df["payment"] == "Рассрочка"]["down_payment"].sum()
        total_real_revenue = revenue_cash + revenue_down

        c1, c2 = st.columns(2)
        c1.metric("💰 Живая Выручка (Нал + Взносы)", f"{total_real_revenue:,.2f} сом")
        c2.metric("📈 Общая Чистая прибыль", f"{filtered_df['profit'].sum():,.2f} сом")

        st.markdown("### 🖨️ Печать и Экспорт")
        excel_df = filtered_df.copy()
        excel_df["В рассрочку"] = excel_df.apply(lambda r: float(r["credit_balance"]) if r["payment"] == "Рассрочка" else 0.0, axis=1)
        excel_df = excel_df.rename(columns={"date": "Дата", "name": "Наименование", "qty": "Кол-во", "total_sale": "Сумма", "down_payment": "Взнос", "payment": "Оплата"})
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            excel_df[["Дата", "Наименование", "Кол-во", "Сумма", "Взнос", "В рассрочку", "Оплата"]].to_excel(writer, index=False)
        
        st.download_button(label="📥 Скачать этот отчёт в Excel", data=buffer.getvalue(), file_name="Otchet.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
        st.dataframe(filtered_df[["date", "name", "qty", "total_sale", "payment"]], use_container_width=True, hide_index=True)

def show_supplier_page():
    st.header("Выплаты поставщикам и контрагентам")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента")
        amount = st.number_input("Сумма выплаты", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                supabase.table("supplier_payments").insert({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "supplier": supplier.strip(), "amount": amount, "comment": comment}).execute()
                st.success("Выплата отправлена!")
                st.rerun()

    payments_res = supabase.table("supplier_payments").select("*").order("id", desc=True).execute()
    if payments_res.data:
        df_pay = pd.DataFrame(payments_res.data).drop(columns=["id", "created_at"], errors="ignore")
        st.dataframe(df_pay, use_container_width=True, hide_index=True)
