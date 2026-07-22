# Магазин «Сулайман-Тоо» — Модуль: Отчеты и Аналитика
# Версия: 1.9 (добавлен Полный отчет + сохранено всё старое)

import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime, timedelta
from database import supabase
from utils import format_date_to_ddmmyyyy, fix_contract_name_on_fly

def show_reports_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    
    if user_role == "Администратор":
        st.header("📊 Аналитика и история продаж (Панель Администратора)")
    else:
        st.header("📋 Ежедневный отчет по продажам (Панель Кассира)")

    # ============================================================
    # ==================== ПОЛНЫЙ ОТЧЁТ (НОВОЕ) ==================
    # ============================================================
    st.subheader("📋 Полный отчет")

    col1, col2 = st.columns(2)
    with col1:
        report_type = st.radio("Тип отчёта", ["За один день", "За период"], horizontal=True, key="full_report_type")
    
    if report_type == "За один день":
        selected_date = st.date_input("Выберите день", value=datetime.now().date(), key="full_report_day")
        start_date = end_date = selected_date
    else:
        date_range = st.date_input(
            "Выберите период",
            value=(datetime.now().date() - timedelta(days=7), datetime.now().date()),
            key="full_report_period"
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            st.warning("Выберите обе даты")
            start_date = end_date = datetime.now().date()

    try:
        sales_res = supabase.table("sales").select("*").execute()
        products_res = supabase.table("products").select("*").execute()
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        sales_res = type('obj', (object,), {'data': []})()
        products_res = type('obj', (object,), {'data': []})()

    sales_data = sales_res.data or []
    products_data = products_res.data or []

    def normalize_day(d):
        if not d:
            return None
        d = str(d)[:10]
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(d, fmt).date()
            except:
                continue
        return None

    sales_rows = []
    for s in sales_data:
        day = normalize_day(s.get("day") or s.get("date"))
        if not day or day < start_date or day > end_date:
            continue
        payment = s.get("payment", "")
        total_sale = float(s.get("total_sale", 0) or 0)
        profit = float(s.get("profit", 0) or 0)
        sales_rows.append({
            "day": day,
            "cash_sale": total_sale if payment == "Наличные" else 0,
            "credit_sale": total_sale if payment == "Рассрочка" else 0,
            "cash_profit": profit if payment == "Наличные" else 0,
            "credit_profit": profit if payment == "Рассрочка" else 0,
        })

    products_rows = []
    for p in products_data:
        day = normalize_day(p.get("date"))
        if not day or day < start_date or day > end_date:
            continue
        products_rows.append({
            "day": day,
            "qty_received": int(p.get("qty", 0) or 0),
            "cost_received": float(p.get("qty", 0) or 0) * float(p.get("cost", 0) or 0)
        })

    if sales_rows or products_rows:
        df_sales = pd.DataFrame(sales_rows) if sales_rows else pd.DataFrame(columns=["day","cash_sale","credit_sale","cash_profit","credit_profit"])
        df_products = pd.DataFrame(products_rows) if products_rows else pd.DataFrame(columns=["day","qty_received","cost_received"])

        sales_daily = df_sales.groupby("day").sum().reset_index() if not df_sales.empty else pd.DataFrame(columns=["day","cash_sale","credit_sale","cash_profit","credit_profit"])
        products_daily = df_products.groupby("day").sum().reset_index() if not df_products.empty else pd.DataFrame(columns=["day","qty_received","cost_received"])

        report = pd.merge(sales_daily, products_daily, on="day", how="outer").fillna(0)
        report = report.sort_values("day")
        report["total_profit"] = report["cash_profit"] + report["credit_profit"]

        display = report.copy()
        display["day"] = display["day"].astype(str)
        display = display.rename(columns={
            "day": "Дата",
            "cash_sale": "Продажи наличкой",
            "credit_sale": "Продажи в рассрочку",
            "qty_received": "Товаров принято (шт)",
            "cost_received": "Сумма принятых",
            "cash_profit": "Прибыль наличные",
            "credit_profit": "Прибыль рассрочка",
            "total_profit": "Общая прибыль"
        })

        for col in display.columns[1:]:
            display[col] = display[col].map("{:,.0f}".format)

        st.dataframe(display, use_container_width=True, hide_index=True)

        st.markdown("##### Итоги за выбранный период")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Продажи наличкой", f"{report['cash_sale'].sum():,.0f} сом")
        c2.metric("Продажи в рассрочку", f"{report['credit_sale'].sum():,.0f} сом")
        c3.metric("Товаров принято", f"{int(report['qty_received'].sum())} шт.")
        c4.metric("Общая прибыль", f"{report['total_profit'].sum():,.0f} сом")

        # Экспорт
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df = report.copy()
            export_df["day"] = export_df["day"].astype(str)
            export_df.to_excel(writer, index=False, sheet_name="Полный отчет")
        excel_buffer.seek(0)

        st.download_button(
            label="📥 Скачать Полный отчет в Excel",
            data=excel_buffer,
            file_name=f"Polnyy_otchet_{start_date}_{end_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    else:
        st.info("За выбранный период данных для Полного отчета нет.")

    st.markdown("---")
    st.markdown("---")

    # ============================================================
    # ==================== СТАРЫЙ РАЗДЕЛ (без изменений) =========
    # ============================================================

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
    
    if user_role == "Администратор":
        st.subheader("🔍 Выберите период для анализа (история продаж)")
        date_range = st.date_input("Диапазон дат", value=(df['day_obj'].min(), df['day_obj'].max()), key="old_report_range")
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

        # ==================== РЕДАКТИРОВАНИЕ ====================
        if user_role == "Администратор":
            st.markdown("---")
            st.subheader("✏️ Редактировать выбранную операцию")

            edit_options = {f"{row['Дата операции']} | {row['Наименование договора / Товара']}": row for idx, row in df_display.iterrows()}
            selected_edit_label = st.selectbox("Выберите операцию для редактирования", ["-- Не выбрано --"] + list(edit_options.keys()))

            if selected_edit_label != "-- Не выбрано --":
                selected_row = edit_options[selected_edit_label]
                sale_id = selected_row["sale_id"]

                sale_data = supabase.table("sales").select("*").eq("id", sale_id).execute().data
                if not sale_data:
                    st.error("Операция не найдена в базе")
                else:
                    sale = sale_data[0]

                    with st.form("edit_sale_form", clear_on_submit=False):
                        new_name = st.text_input("Наименование договора / Товара", value=str(sale.get("name", "")))
                        new_qty = st.number_input("Количество", min_value=0, value=int(sale.get("qty", 0)))
                        new_total_sale = st.number_input("Сумма продажи (сом)", min_value=0, value=int(sale.get("total_sale", 0)))
                        new_total_cost = st.number_input("Себестоимость (сом)", min_value=0, value=int(sale.get("total_cost", 0)))

                        new_profit = new_total_sale - new_total_cost
                        st.markdown(f"**Прибыль (будет пересчитана):** `{new_profit:,} сом`")

                        col1, col2 = st.columns(2)
                        with col1:
                            new_payment = st.selectbox("Тип оплаты", ["Наличные", "Рассрочка"], 
                                                       index=0 if sale.get("payment") == "Наличные" else 1)
                        with col2:
                            new_down_payment = st.number_input("Перв. взнос (сом)", min_value=0, 
                                                               value=int(sale.get("down_payment", 0) or 0))

                        new_credit_balance = st.number_input("Остаток в рассрочку (сом)", min_value=0, 
                                                             value=int(sale.get("credit_balance", 0) or 0))

                        if st.form_submit_button("💾 Сохранить изменения", type="primary"):
                            try:
                                update_data = {
                                    "name": new_name.strip(),
                                    "qty": new_qty,
                                    "total_sale": new_total_sale,
                                    "total_cost": new_total_cost,
                                    "profit": new_profit,
                                    "payment": new_payment,
                                    "down_payment": new_down_payment,
                                    "credit_balance": new_credit_balance
                                }
                                supabase.table("sales").update(update_data).eq("id", sale_id).execute()
                                st.success("✅ Изменения успешно сохранены!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Ошибка при сохранении: {e}")

        # ==================== ОТМЕНА ПРОДАЖ ====================
        if user_role == "Администратор":
            st.markdown("---")
            st.subheader("⚙️ Управление и отмена продаж")
            
            cancel_options = {f"{row['Дата операции']} | {row['Наименование договора / Товара']}": row for idx, row in df_display.iterrows()}
            selected_to_cancel = st.selectbox("🚫 Выберите операцию для отмены:", ["-- Не выбрано --"] + list(cancel_options.keys()))
            
            if selected_to_cancel != "-- Не выбрано --":
                s_del = cancel_options[selected_to_cancel]
                
                if st.button("🚨 Подтвердить и БЕЗВОЗВРАТНО УДАЛИТЬ продажу", type="primary", use_container_width=True):
                    with st.spinner("⏳ Выполняется отмена..."):
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
                                match_items = re.search(r"Товары:\s*(.*?)\)", s_del["Наименование договора / Товара"])
                                if match_items:
                                    for part in match_items.group(1).split(", "):
                                        item_match = re.search(r"(.*)\s+\((\d+)\s+шт\.\)", part)
                                        if item_match:
                                            p_name = item_match.group(1).strip().lower()
                                            p_qty = int(item_match.group(2))
                                            
                                            b_res = supabase.table("products").select("id", "qty").eq("name", p_name).order("date", desc=True).execute()
                                            if b_res.data:
                                                supabase.table("products").update({"qty": int(b_res.data[0]["qty"]) + p_qty}).eq("id", b_res.data[0]["id"]).execute()
                            
                            supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                            supabase.table("credit_payments").delete().eq("sale_id", s_del["sale_id"]).execute()
                            
                            if int(s_del["Перв. взнос (Нал)"]) > 0:
                                supabase.table("cash_operations").delete().eq("amount", float(s_del["Перв. взнос (Нал)"])).execute()
                                
                            st.success("🎉 Операция успешно отменена!")
                            st.rerun()
                        except Exception as e: 
                            st.error(f"Ошибка при удалении: {e}")
    else:
        st.info("Сегодня продаж еще не зафиксировано.")


def show_supplier_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    if user_role != "Администратор": 
        return
        
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
