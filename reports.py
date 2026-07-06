# Магазин «Сулайман-Тоо» — Модуль: Отчеты и Аналитика
# Версия программы: 1.4 (Внедрена защита отмены продаж для роли Кассир)

import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime
from database import supabase

def format_any_date(date_str, include_time=False):
    """Универсальная функция перевода дат из YYYY-MM-DD в ДД.ММ.ГГГГ на экране"""
    if not date_str:
        return "-"
    date_str = str(date_str).strip()
    
    if "." in date_str[:10]:
        return date_str
        
    try:
        if " " in date_str:
            date_part, time_part = date_str.split(" ")
            parsed_d = datetime.strptime(date_part, "%Y-%m-%d").strftime("%d.%m.%Y")
            return f"{parsed_d} {time_part}" if include_time else parsed_d
        else:
            parsed_d = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
            return parsed_d
    except:
        return date_str

def fix_contract_name_on_fly(name_str, date_str):
    """Автоматически заменяет ошибочный номер №202607 на дату продажи на экране"""
    if not name_str:
        return name_str
    
    if "№202607" in str(name_str):
        clean_date = format_any_date(date_str, include_time=False)
        new_num = clean_date.replace(".", "")[:4]
        return str(name_str).replace("№202607", f"№{new_num}")
    return name_str

def show_reports_page():
    st.header("📊 Аналитика и история продаж")
    
    sales_all = supabase.table("sales").select("*").order("date", desc=True).execute()
    
    if not sales_all.data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_all.data)
    
    def parse_day_for_filter(x):
        try:
            if "." in str(x):
                return datetime.strptime(str(x)[:10], "%d.%m.%Y").date()
            return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
        except:
            return datetime.now().date()
            
    df['day_obj'] = df['day'].apply(parse_day_for_filter)
    
    st.subheader("🔍 Выберите период для анализа")
    date_range = st.date_input("Диапазон дат", value=(df['day_obj'].min(), df['day_obj'].max()))
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = df[(df['day_obj'] >= start_date) & (df['day_obj'] <= end_date)]
        
        # Расчёт финансовых показателей
        total_sales_cash = filtered_df[filtered_df['payment'] == 'Наличные']['total_sale'].sum()
        total_down_payments = filtered_df[filtered_df['payment'] == 'Рассрочка']['down_payment'].sum()
        
        # Извлекаем операции погашений
        ops_res = supabase.table("cash_operations").select("*").execute()
        total_credit_collected = 0.0
        if ops_res.data:
            for op in ops_res.data:
                try:
                    op_date_str = op["date"]
                    if "." in op_date_str[:10]:
                        op_day = datetime.strptime(op_date_str[:10], "%d.%m.%Y").date()
                    else:
                        op_day = datetime.strptime(op_date_str[:10], "%Y-%m-%d").date()
                    if start_date <= op_day <= end_date and "Погашение рассрочки" in str(op.get("comment", "")):
                        total_credit_collected += float(op["amount"])
                except: continue

        total_revenue = total_sales_cash + total_down_payments + total_credit_collected
        total_cost = filtered_df['total_cost'].sum()
        
        # Расчёт раздельной прибыли
        cash_profit = filtered_df[filtered_df['payment'] == 'Наличные']['profit'].sum()
        credit_profit = 0.0
        for _, row in filtered_df[filtered_df['payment'] == 'Рассрочка'].iterrows():
            credit_profit += (float(row.get("down_payment", 0)) + float(row.get("credit_balance", 0))) - float(row.get("total_cost", 0))
        total_profit_combined = cash_profit + credit_profit

        st.markdown("---")
        st.markdown("#### 🟢 Прямые продажи (Наличные)")
        col_c1, col_c2 = st.columns(2)
        col_c1.metric("Сумма продаж (Нал)", f"{int(cash_turnover if 'cash_turnover' in locals() else cash_profit):,} сом")
        col_c2.metric("Чистая прибыль (Нал)", f"{int(cash_profit):,} сом")
        
        st.markdown("#### 🔵 Продажи в рассрочку (Прогноз)")
        col_r1, col_r2 = st.columns(2)
        col_r1.metric("Общая сумма чеков рассрочки", f"{int(credit_turnover if 'credit_turnover' in locals() else credit_profit):,} сом")
        col_r2.metric("Ожидаемая прибыль (+наценка 3%/мес)", f"{int(credit_profit):,} сом")
        
        st.markdown("#### #### 🏛️ Итоговые показатели по магазину")
        col_t1, col_t2 = st.columns(2)
        col_t1.metric("🔥 Общий оборот продаж", f"{int(total_sales_cash + credit_turnover if 'credit_turnover' in locals() else total_revenue):,} сом")
        col_t2.metric("📈 Суммарная чистая прибыль", f"{int(total_profit_combined):,} сом")

        st.markdown("---")
        st.subheader("📋 Детализация списка продаж")
        
        if not filtered_df.empty:
            report_display = []
            for _, row in filtered_df.iterrows():
                fixed_name = fix_contract_name_on_fly(row['name'], row['date'])
                if row['payment'] == 'Рассрочка':
                    row_profit = (int(row.get('down_payment', 0) or 0) + int(row.get('credit_balance', 0) or 0)) - int(row['total_cost'])
                else:
                    row_profit = int(row['profit'])

                report_display.append({
                    "Дата операции": format_any_date(row['date'], include_time=True),
                    "Наименование договора / Товара": fixed_name,
                    "Кол-во": int(row['qty']),
                    "Тип оплаты": row['payment'],
                    "Закупка (сом)": int(row['total_cost']),
                    "Продажа (сом)": int(row['total_sale']),
                    "Взнос (Нал)": int(row.get('down_payment', 0) or 0),
                    "Остаток долга (+наценка)": int(row.get('credit_balance', 0) or 0),
                    "Прибыль (сом)": int(row_profit),
                    "sale_id": row['id'],
                    "raw_payment": row['payment']
                })
            
            df_display = pd.DataFrame(report_display)
            st.dataframe(df_display.drop(columns=["sale_id", "raw_payment"]), use_container_width=True, hide_index=True)
            
            # БЛОК УМНОЙ ОТМЕНЫ С ЗАЩИТОЙ РОЛЕЙ
            st.markdown("---")
            st.subheader("⚙️ Управление и отмена продаж")
            
            if st.session_state.get("user_role") == "Кассир":
                st.warning("🔒 Функция отмены сделок и безвозвратного удаления чеков доступна только Администратору.")
            else:
                cancel_options = {f"{row['Дата операции']} | {row['Наименование договора / Товара']}": row for idx, row in df_display.iterrows()}
                selected_to_cancel = st.selectbox("🚫 Выберите операцию для её полной отмены и возврата остатков:", ["-- Не выбрано --"] + list(cancel_options.keys()))
                
                if selected_to_cancel != "-- Не выбрано --":
                    s_del = cancel_options[selected_to_cancel]
                    if st.button("🚨 Подтвердить и БЕЗВОЗВРАТНО УДАЛИТЬ продажу", type="primary", use_container_width=True):
                        try:
                            if s_del["raw_payment"] == "Наличные":
                                match = re.search(r"\(приход\s+([\d\.-]+)\)", s_del["Наименование договора / Товара"])
                                if match:
                                    b_date_raw = match.group(1)
                                    b_date = datetime.strptime(b_date_raw, "%d.%m.%Y").date().strftime("%Y-%m-%d") if "." in b_date_raw else b_date_raw
                                    p_name = str(s_del["Наименование договора / Товара"]).split(" (приход")[0].strip().lower()
                                    batch_res = supabase.table("products").select("id", "qty").eq("name", p_name).eq("date", b_date).execute()
                                    if batch_res.data:
                                        supabase.table("products").update({"qty": int(batch_res.data[0]["qty"]) + int(s_del["Кол-во"])}).eq("id", batch_res.data[0]["id"]).execute()
                                    
                            elif s_del["raw_payment"] == "Рассрочка":
                                match_items = re.search(r"\[(.*?)\]", s_del["Наименование договора / Товара"])
                                if match_items:
                                    for part in match_items.group(1).split(", "):
                                        item_match = re.search(r"(.*)\s+\((\d+)\s+шт\.\)", part)
                                        if item_match:
                                            p_name = item_match.group(1).strip().lower()
                                            b_res = supabase.table("products").select("id", "qty").eq("name", p_name).gt("qty", 0).order("date", desc=True).execute()
                                            if b_res.data:
                                                supabase.table("products").update({"qty": int(b_res.data[0]["qty"]) + int(item_match.group(2))}).eq("id", b_res.data[0]["id"]).execute()
                                
                            supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                            supabase.table("credit_payments").delete().eq("sale_id", s_del["sale_id"]).execute()
                            st.success("🎉 Операция успешно отменена!")
                            st.rerun()
                        except Exception as e: st.error(f"Ошибка при удалении продажи: {e}")
