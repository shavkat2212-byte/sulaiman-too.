# Магазин «Сулайман-Тоо» — Модуль: Отчеты и Аналитика
# Версия программы: 1.8.1 (Убрал дашборд, добавил кэширование)

import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime
from database import supabase

from utils import format_date_to_ddmmyyyy, fix_contract_name_on_fly

@st.cache_data(ttl=30)
def get_sales_data():
    return supabase.table("sales").select("*").order("date", desc=True).execute().data

def show_reports_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    
    if user_role == "Администратор":
        st.header("📊 Аналитика и история продаж (Панель Администратора)")
    else:
        st.header("📋 Ежедневный отчет по продажам (Панель Кассира)")

    sales_data = get_sales_data()
    if not sales_data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_data)
    
    def parse_day_for_filter(x):
        try:
            if "." in str(x): 
                return datetime.strptime(str(x)[:10], "%d.%m.%Y").date()
            return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
        except: 
            return datetime.now().date()
            
    df['day_obj'] = df['day'].apply(parse_day_for_filter)
    
    if user_role == "Администратор":
        st.subheader("🔍 Выберите период для анализа")
        date_range = st.date_input("Диапазон дат", value=(df['day_obj'].min(), df['day_obj'].max()))
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[(df['day_obj'] >= start_date) & (df['day_obj'] <= end_date)]
        else: 
            filtered_df = pd.DataFrame()
    else:
        today_date = datetime.now().date()
        filtered_df = df[df['day_obj'] == today_date]
        st.info(f"📅 Отображаются операции за сегодня: **{today_date.strftime('%d.%m.%Y')}**")

    if not filtered_df.empty:
        # Метрики
        df_cash = filtered_df[filtered_df['payment'] == 'Наличные']
        cash_turnover = float(df_cash['total_sale'].sum()) if not df_cash.empty else 0.0
        df_credit = filtered_df[filtered_df['payment'] == 'Рассрочка']
        credit_turnover = float(df_credit['total_sale'].sum()) if not df_credit.empty else 0.0
        total_turnover = cash_turnover + credit_turnover

        st.markdown("---")
        if user_role == "Администратор":
            cash_profit = float(df_cash['profit'].sum()) if not df_cash.empty else 0.0
            credit_profit = 0.0
            if not df_credit.empty:
                for _, row in df_credit.iterrows():
                    cost = float(row.get("total_cost", 0) or 0)
                    down = float(row.get("down_payment", 0) or 0)
                    balance_markup = float(row.get("credit_balance", 0) or 0)
                    credit_profit += (down + balance_markup) - cost
            total_profit_combined = cash_profit + credit_profit

            col_t1, col_t2, col_t3 = st.columns(3)
            col_t1.metric("💵 Оборот (Наличные)", f"{int(cash_turnover):,} сом")
            col_t2.metric("📦 Оборот (Рассрочка)", f"{int(credit_turnover):,} сом")
            col_t3.metric("🔥 Общий оборот", f"{int(total_turnover):,} сом")
            
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("📈 Прибыль (Нал)", f"{int(cash_profit):,} сом")
            col_p2.metric("📈 Прибыль (Рассрочка)", f"{int(credit_profit):,} сом")
            col_p3.metric("🏆 Суммарная прибыль", f"{int(total_profit_combined):,} сом")
        else:
            col_k1, col_k2, col_k3 = st.columns(3)
            col_k1.metric("🟢 Продажи за сегодня (Нал)", f"{int(cash_turnover):,} сом")
            col_k2.metric("🔵 Оформлено рассрочек сегодня", f"{int(credit_turnover):,} сом")
            col_k3.metric("🛍️ Общая выручка за день", f"{int(total_turnover):,} сом")

        st.markdown("---")
        st.subheader("📋 Список оформленных чеков")

        # Экспорт
        if user_role == "Администратор":
            col_btn1, col_btn2 = st.columns([5, 2])
            with col_btn2:
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    export_data = []
                    for _, row in filtered_df.iterrows():
                        export_data.append({
                            "Дата операции": format_date_to_ddmmyyyy(row['date'], include_time=True),
                            "Наименование": fix_contract_name_on_fly(row['name'], row['date']),
                            "Кол-во": int(row['qty']),
                            "Тип оплаты": row['payment'],
                            "Сумма продажи (сом)": int(row['total_sale']),
                            "Прибыль (сом)": int(row.get('profit', 0)),
                            "Перв. взнос": int(row.get('down_payment', 0) or 0),
                            "Остаток рассрочки": int(row.get('credit_balance', 0) or 0)
                        })
                    pd.DataFrame(export_data).to_excel(writer, index=False, sheet_name="Продажи")
                excel_buffer.seek(0)
                st.download_button(
                    label="📥 Скачать в Excel",
                    data=excel_buffer,
                    file_name=f"Отчет_продажи_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        # Таблица
        report_display = []
        for _, row in filtered_df.iterrows():
            fixed_name = fix_contract_name_on_fly(row['name'], row['date'])
            item_data = {
                "Дата операции": format_date_to_ddmmyyyy(row['date'], include_time=True),
                "Наименование договора / Товара": fixed_name,
                "Кол-во": int(row['qty']),
                "Тип оплаты": row['payment'],
                "Сумма продажи (сом)": int(row['total_sale']),
                "Перв. взнос (Нал)": int(row.get('down_payment', 0) or 0),
                "Остаток в рассрочку": int(row.get('credit_balance', 0) or 0),
                "sale_id": row['id'],
                "raw_payment": row['payment']
            }
            if user_role == "Администратор":
                item_data["Закупка (сом)"] = int(row['total_cost'])
                item_data["Прибыль (сом)"] = int(row.get('profit', 0))
            report_display.append(item_data)
        
        df_display = pd.DataFrame(report_display)
        cols_to_drop = ["sale_id", "raw_payment"]
        st.dataframe(df_display.drop(columns=cols_to_drop, errors="ignore"), use_container_width=True, hide_index=True)

        # Редактирование и отмена (оставил без изменений)
        if user_role == "Администратор":
            st.markdown("---")
            st.subheader("✏️ Редактировать выбранную операцию")
            # ... (код редактирования оставлен как был)
            # Если нужно, могу выдать полный блок отдельно

        if user_role == "Администратор":
            st.markdown("---")
            st.subheader("⚙️ Управление и отмена продаж")
            # ... (код отмены оставлен как был)

    else:
        st.info("Сегодня продаж еще не зафиксировано.")
