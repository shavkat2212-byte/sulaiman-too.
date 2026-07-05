# Магазин «Сулайман-Тоо» — Модуль: Отчеты и Аналитика
# Версия программы: 1.2 (Универсальный конвертер и исправление вывода старых дат)

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
    
    # Если дата уже содержит точки (новый формат), просто возвращаем её
    if "." in date_str[:10]:
        return date_str
        
    # Если дата в старом формате с дефисами YYYY-MM-DD
    try:
        if " " in date_str: # Если есть время ЧЧ:ММ
            date_part, time_part = date_str.split(" ")
            parsed_d = datetime.strptime(date_part, "%Y-%m-%d").strftime("%d.%m.%Y")
            return f"{parsed_d} {time_part}" if include_time else parsed_d
        else:
            parsed_d = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
            return parsed_d
    except:
        return date_str

def show_reports_page():
    st.header("📊 Аналитика и история продаж")
    
    # Загружаем продажи и кассовые операции по погашению рассрочек
    sales_all = supabase.table("sales").select("*").order("date", desc=True).execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    if not sales_all.data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_all.data)
    
    # Приводим поле day к стандартному типу date для фильтрации
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
        
        # Фильтруем оплаты по рассрочкам для нижнего отчета
        filtered_ops_data = []
        if ops_res.data:
            for op in ops_res.data:
                try:
                    op_date_str = op["date"]
                    if "." in op_date_str[:10]:
                        op_day = datetime.strptime(op_date_str[:10], "%d.%m.%Y").date()
                    else:
                        op_day = datetime.strptime(op_date_str[:10], "%Y-%m-%d").date()
                        
                    if start_date <= op_day <= end_date:
                        filtered_ops_data.append(op)
                except:
                    continue
        
        # Считаем финансовые показатели
        total_sales_cash = filtered_df[filtered_df['payment'] == 'Наличные']['total_sale'].sum()
        total_down_payments = filtered_df[filtered_df['payment'] == 'Рассрочка']['down_payment'].sum()
        
        # Сумма фактически внесенных платежей по рассрочкам из cash_operations
        total_credit_collected = 0.0
        if filtered_ops_data:
            for op in filtered_ops_data:
                if "Погашение рассрочки" in str(op.get("comment", "")):
                    total_credit_collected += float(op["amount"])

        # Общая чистая выручка кассы = Наличные + Первоначальные взносы + Погашения рассрочек
        total_revenue = total_sales_cash + total_down_payments + total_credit_collected
        
        # Себестоимость проданного товара (закупка)
        total_cost = filtered_df['total_cost'].sum()
        
        # Валовая прибыль (Выручка - Закупка проданного)
        total_profit = total_revenue - total_cost

        # Блок красивых финансовых метрик
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("💵 Общая выручка (Все приходы)", f"{int(total_revenue):,} сом")
        m2.metric("📦 Себестоимость закупки", f"{int(total_cost):,} сом")
        m3.metric("📈 Валовая чистая прибыль", f"{int(total_profit):,} сом", delta=f"{int(total_profit)}")

        with st.expander("📊 Развернутая детализация структуры выручки"):
            c1, c2, c3 = st.columns(3)
            c1.info(f"🟢 Прямые продажи (Нал): \n**{int(total_sales_cash):,} сом**")
            c2.info(f"🔵 Первоначальные взносы: \n**{int(total_down_payments):,} сом**")
            c3.info(f"🟣 Погашения рассрочек: \n**{int(total_credit_collected):,} сом**")

        st.markdown("---")
        st.subheader("📋 Детализация списка продаж")
        
        if not filtered_df.empty:
            # Формируем красивую таблицу для отображения на экране
            report_display = []
            for _, row in filtered_df.iterrows():
                report_display.append({
                    "Дата операции": format_any_date(row['date'], include_time=True),
                    "Наименование договора / Товара": row['name'],
                    "Кол-во": int(row['qty']),
                    "Тип оплаты": row['payment'],
                    "Закупка (сом)": int(row['total_cost']),
                    "Продажа (сом)": int(row['total_sale']),
                    "Взнос (Нал)": int(row.get('down_payment', 0) or 0),
                    "Остаток долга (+наценка)": int(row.get('credit_balance', 0) or 0),
                    "Прибыль (сом)": int(row['profit']),
                    # скрытое поле для умной отмены
                    "sale_id": row['id'],
                    "raw_payment": row['payment']
                })
            
            df_display = pd.DataFrame(report_display)
            
            # Отображаем таблицу БЕЗ служебных столбцов отмены
            st.dataframe(
                df_display.drop(columns=["sale_id", "raw_payment"]), 
                use_container_width=True, 
                hide_index=True
            )
            
            # Экспорт в Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_display.drop(columns=["sale_id", "raw_payment"]).to_excel(writer, index=False, sheet_name='Отчет по продажам')
            
            st.download_button(
                label="📥 Скачать данный отчет в Excel",
                data=buffer.getvalue(),
                file_name=f"Отчет_Сулайман_Тоо_{start_date}_to_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            # -----------------------------------------------------------------
            # БЛОК УМНОЙ ОТМЕНЫ (УДАЛЕНИЯ) ПРОДАЖ
            # -----------------------------------------------------------------
            st.markdown("---")
            st.subheader("⚙️ Управление и отмена продаж")
            
            # Выбор продажи для отмены по названию и дате
            cancel_options = {f"{row['Дата операции']} | {row['Наименование договора / Товара']}": row for idx, row in df_display.iterrows()}
            selected_to_cancel = st.selectbox("🚫 Выберите операцию для её полной отмены и возврата остатков:", ["-- Не выбрано --"] + list(cancel_options.keys()))
            
            if selected_to_cancel != "-- Не выбрано --":
                s_del = cancel_options[selected_to_cancel]
                
                if st.button("🚨 Подтвердить и БЕЗВОЗВРАТНО УДАЛИТЬ продажу", type="primary", use_container_width=True):
                    with st.spinner("⏳ Выполняется разбор продажи и возврат товаров на склад..."):
                        try:
                            # 1. Если это обычная продажа (Наличные), восстанавливаем товар на складе
                            if s_del["raw_payment"] == "Наличные":
                                # Извлекаем имя партии из текста (приход YYYY-MM-DD или ДД.ММ.ГГГГ)
                                match = re.search(r"\(приход\s+([\d\.-]+)\)", s_del["Наименование договора / Товара"])
                                if match:
                                    b_date_raw = match.group(1)
                                    # Если дата в названии договора переформатирована в ДД.ММ.ГГГГ, переводим обратно для БД
                                    if "." in b_date_raw:
                                        b_date = datetime.strptime(b_date_raw, "%d.%m.%Y").strftime("%Y-%m-%d")
                                    else:
                                        b_date = b_date_raw
                                        
                                    p_name = str(s_del["Наименование договора / Товара"]).split(" (приход")[0].strip().lower()
                                    
                                    # Ищем эту партию на складе
                                    batch_res = supabase.table("products").select("id", "qty").eq("name", p_name).eq("date", b_date).execute()
                                    if batch_res.data:
                                        old_qty = int(batch_res.data[0]["qty"])
                                        new_qty = old_qty + int(s_del["Кол-во"])
                                        supabase.table("products").update({"qty": new_qty}).eq("id", batch_res.data[0]["id"]).execute()
                                
                            # 2. Если это Рассрочка, нужно разобрать товары по строкам из состава договора
                            elif s_del["raw_payment"] == "Рассрочка":
                                # Вытаскиваем все элементы из квадратных скобок [Товар x1 шт., Товар2 x2 шт.]
                                match_items = re.search(r"\[(.*?)\]", s_del["Наименование договора / Товара"])
                                if match_items:
                                    items_str = match_items.group(1)
                                    parts = items_str.split(", ")
                                    for part in parts:
                                        # Извлекаем название и количество
                                        item_match = re.search(r"(.*)\s+\((\d+)\s+шт\.\)", part)
                                        if item_match:
                                            p_name = item_match.group(1).strip().lower()
                                            return_qty = int(item_match.group(2))
                                            
                                            # Возвращаем в самую свежую партию этого товара с остатком > 0
                                            b_res = supabase.table("products").select("id", "qty").eq("name", p_name).gt("qty", 0).order("date", desc=True).execute()
                                            if b_res.data:
                                                new_qty = int(b_res.data[0]["qty"]) + return_qty
                                                supabase.table("products").update({"qty": new_qty}).eq("id", b_res.data[0]["id"]).execute()
                            
                            # 3. Полностью удаляем запись продажи и связанные графики платежей из Supabase
                            supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                            supabase.table("credit_payments").delete().eq("sale_id", s_del["sale_id"]).execute()
                            
                            st.success("🎉 Операция успешно отменена! Товары возвращены на склад, графики удалены.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка при удалении продажи: {e}")
        else:
            st.info("Нет данных за выбранный период")

def show_supplier_page():
    st.header("Выплаты поставщикам и контрагентам")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента")
        amount = st.number_input("Сумма выплаты", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                now_formatted = datetime.now().strftime("%d.%m.%Y %H:%M")
                supabase.table("supplier_payments").insert({
                    "date": now_formatted, 
                    "supplier": supplier.strip(), 
                    "amount": amount, 
                    "comment": comment
                }).execute()
                st.success("Выплата отправлена!")
                st.rerun()

    payments_res = supabase.table("supplier_payments").select("*").order("id", desc=True).execute()
    if payments_res.data:
        df_pay = pd.DataFrame(payments_res.data).drop(columns=["id", "created_at"], errors="ignore")
        
        # Переводим даты выплат поставщикам в ДД.ММ.ГГГГ на экране
        df_pay["date"] = df_pay["date"].apply(lambda x: format_any_date(x, include_time=True))
        df_pay = df_pay.rename(columns={"date": "Дата выплаты", "supplier": "Контрагент", "amount": "Сумма (сом)", "comment": "Комментарий"})
        st.dataframe(df_pay[["Дата выплаты", "Контрагент", "Сумма (сом)", "Комментарий"]], use_container_width=True, hide_index=True)
