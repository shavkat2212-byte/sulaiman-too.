# Магазин «Сулайман-Тоо» — Модуль: Отчеты и Аналитика
# Версия программы: 1.7.5 (Исправлен парсинг круглых скобок для точной отмены рассрочек)

import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime
from database import supabase

def format_any_date(date_str, include_time=False):
    if not date_str: return "-"
    date_str = str(date_str).strip()
    if "." in date_str[:10]: return date_str
    try:
        if " " in date_str:
            date_part, time_part = date_str.split(" ")
            parsed_d = datetime.strptime(date_part, "%Y-%m-%d").strftime("%d.%m.%Y")
            return f"{parsed_d} {time_part}" if include_time else parsed_d
        else:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except: return date_str

def fix_contract_name_on_fly(name_str, date_str):
    if not name_str: return name_str
    if "№202607" in str(name_str):
        clean_date = format_any_date(date_str, include_time=False)
        new_num = clean_date.replace(".", "")[:4]
        return str(name_str).replace("№202607", f"№{new_num}")
    return name_str

def show_reports_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    
    if user_role == "Администратор":
        st.header("📊 Аналитика и история продаж (Панель Администратора)")
    else:
        st.header("📋 Ежедневный отчет по продажам (Панель Кассира)")

    sales_all = supabase.table("sales").select("*").order("date", desc=True).execute()
    if not sales_all.data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_all.data)
    
    def parse_day_for_filter(x):
        try:
            if "." in str(x): return datetime.strptime(str(x)[:10], "%d.%m.%Y").date()
            return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
        except: return datetime.now().date()
            
    df['day_obj'] = df['day'].apply(parse_day_for_filter)
    
    if user_role == "Администратор":
        st.subheader("🔍 Выберите период для анализа")
        date_range = st.date_input("Диапазон дат", value=(df['day_obj'].min(), df['day_obj'].max()))
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[(df['day_obj'] >= start_date) & (df['day_obj'] <= end_date)]
        else: filtered_df = pd.DataFrame()
    else:
        today_date = datetime.now().date()
        filtered_df = df[df['day_obj'] == today_date]
        st.info(f"📅 Отображаются операции за сегодня: **{today_date.strftime('%d.%m.%Y')}**")

    if not filtered_df.empty:
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
        
        report_display = []
        for _, row in filtered_df.iterrows():
            fixed_name = fix_contract_name_on_fly(row['name'], row['date'])
            item_data = {
                "Дата операции": format_any_date(row['date'], include_time=True),
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
                if row['payment'] == 'Рассрочка':
                    row_profit = (int(row.get('down_payment', 0) or 0) + int(row.get('credit_balance', 0) or 0)) - int(row['total_cost'])
                else: row_profit = int(row['profit'])
                item_data["Закупка (сом)"] = int(row['total_cost'])
                item_data["Прибыль (сом)"] = int(row_profit)
            report_display.append(item_data)
        
        df_display = pd.DataFrame(report_display)
        cols_to_drop = ["sale_id", "raw_payment"]
        st.dataframe(df_display.drop(columns=cols_to_drop, errors="ignore"), use_container_width=True, hide_index=True)
        
        # --- БЛОК ОКОНЧАТЕЛЬНОЙ ОТМЕНЫ (УСПЕШНО ЧИТАЕТ КРУГЛЫЕ СКОБКИ) ---
        if user_role == "Администратор":
            st.markdown("---")
            st.subheader("⚙️ Управление и отмена продаж")
            
            cancel_options = {f"{row['Дата операции']} | {row['Наименование договора / Товара']}": row for idx, row in df_display.iterrows()}
            selected_to_cancel = st.selectbox("🚫 Выберите операцию для её полной отмены и возврата остатков:", ["-- Не выбрано --"] + list(cancel_options.keys()))
            
            if selected_to_cancel != "-- Не выбрано --":
                s_del = cancel_options[selected_to_cancel]
                
                if st.button("🚨 Подтвердить и БЕЗВОЗВРАТНО УДАЛИТЬ продажу", type="primary", use_container_width=True):
                    with st.spinner("⏳ Выполняется разбор продажи и возврат товаров на склад..."):
                        try:
                            # 1. Отмена наличных продаж
                            if s_del["raw_payment"] == "Наличные":
                                match = re.search(r"\(приход\s+([\d\.-]+)\)", s_del["Наименование договора / Товара"])
                                if match:
                                    b_date_raw = match.group(1)
                                    b_date = datetime.strptime(b_date_raw, "%d.%m.%Y").date().strftime("%Y-%m-%d") if "." in b_date_raw else b_date_raw
                                    p_name = str(s_del["Наименование договора / Товара"]).split(" (приход")[0].strip().lower()
                                    
                                    batch_res = supabase.table("products").select("id", "qty").eq("name", p_name).eq("date", b_date).execute()
                                    if batch_res.data:
                                        supabase.table("products").update({"qty": int(batch_res.data[0]["qty"]) + int(s_del["Кол-во"])}).eq("id", batch_res.data[0]["id"]).execute()
                                
                            # 2. Отмена рассрочек (ИСПРАВЛЕНО НА КРУГЛЫЕ СКОБКИ)
                            elif s_del["raw_payment"] == "Рассрочка":
                                # Ищем всё, что находится после слова "Товары: " внутри круглых скобок
                                match_items = re.search(r"Товары:\s*(.*?)\)", s_del["Наименование договора / Товара"])
                                if match_items:
                                    # Разбиваем строку, если товаров было несколько через запятую
                                    for part in match_items.group(1).split(", "):
                                        item_match = re.search(r"(.*)\s+\((\d+)\s+шт\.\)", part)
                                        if item_match:
                                            p_name = item_match.group(1).strip().lower()
                                            p_qty = int(item_match.group(2))
                                            
                                            # Возвращаем остаток к последней активной партии товара
                                            b_res = supabase.table("products").select("id", "qty").eq("name", p_name).order("date", desc=True).execute()
                                            if b_res.data:
                                                supabase.table("products").update({"qty": int(b_res.data[0]["qty"]) + p_qty}).eq("id", b_res.data[0]["id"]).execute()
                            
                            # Удаляем записи из таблиц продаж и графика
                            supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                            supabase.table("credit_payments").delete().eq("sale_id", s_del["sale_id"]).execute()
                            
                            # Удаляем запись о перв. взносе из кассы, если он был
                            if int(s_del["Перв. взнос (Нал)"]) > 0:
                                supabase.table("cash_operations").delete().eq("amount", float(s_del["Перв. взнос (Нал)"])).execute()
                                
                            st.success("🎉 Операция успешно отменена, товары возвращены на склад!")
                            st.rerun()
                        except Exception as e: st.error(f"Ошибка при удалении продажи: {e}")
    else:
        st.info("Сегодня продаж еще не зафиксировано.")

def show_supplier_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    if user_role != "Администратор": return
        
    st.header("Выплаты поставщикам и контрагентам")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента")
        amount = st.number_input("Сумма выплаты", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                now_formatted = datetime.now().strftime("%d.%m.%Y %H:%M")
                supabase.table("supplier_payments").insert({
                    "date": now_formatted, "supplier": supplier.strip(), "amount": amount, "comment": comment
                }).execute()
                st.success("Выплата отправлена!")
                st.rerun()
