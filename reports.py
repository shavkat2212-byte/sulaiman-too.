# Магазин «Сулайман-Тоо» — Модуль: Отчеты
# Версия: 2.1 (полное редактирование + отмена + Полный отчет)

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

    try:
        sales_all = supabase.table("sales").select("*").order("date", desc=True).execute()
        products_all = supabase.table("products").select("*").execute()
    except Exception as e:
        st.error(f"Ошибка: {e}")
        return

    if not sales_all.data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_all.data)
    products_data = products_all.data or []

    def parse_day(x):
        try:
            x = str(x)[:10]
            if "." in x:
                return datetime.strptime(x, "%d.%m.%Y").date()
            return datetime.strptime(x, "%Y-%m-%d").date()
        except:
            return None

    df['day_obj'] = df['day'].apply(parse_day)

    # ===== ВЫБОР ПЕРИОДА =====
    if user_role == "Администратор":
        st.subheader("🔍 Выберите период")
        date_range = st.date_input("Диапазон дат", value=(df['day_obj'].min(), df['day_obj'].max()), key="main_period")
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[(df['day_obj'] >= start_date) & (df['day_obj'] <= end_date)].copy()
        else:
            filtered_df = pd.DataFrame()
    else:
        today = datetime.now().date()
        filtered_df = df[df['day_obj'] == today].copy()
        st.info(f"📅 Продажи за сегодня: **{today.strftime('%d.%m.%Y')}**")

    if filtered_df.empty:
        st.info("За выбранный период продаж нет.")
        return

    # ===== МЕТРИКИ =====
    df_cash = filtered_df[filtered_df['payment'] == 'Наличные']
    df_credit = filtered_df[filtered_df['payment'] == 'Рассрочка']

    cash_turnover = float(df_cash['total_sale'].sum()) if not df_cash.empty else 0
    credit_turnover = float(df_credit['total_sale'].sum()) if not df_credit.empty else 0

    cash_profit = float((df_cash['total_sale'] - df_cash['total_cost']).sum()) if not df_cash.empty else 0
    credit_profit = 0
    if not df_credit.empty:
        for _, row in df_credit.iterrows():
            cost = float(row.get("total_cost", 0) or 0)
            down = float(row.get("down_payment", 0) or 0)
            bal = float(row.get("credit_balance", 0) or 0)
            credit_profit += (down + bal) - cost

    total_profit = cash_profit + credit_profit

    st.markdown("---")
    if user_role == "Администратор":
        c1, c2, c3 = st.columns(3)
        c1.metric("💵 Оборот (Наличные)", f"{int(cash_turnover):,} сом")
        c2.metric("📦 Оборот (Рассрочка)", f"{int(credit_turnover):,} сом")
        c3.metric("🔥 Общий оборот", f"{int(cash_turnover + credit_turnover):,} сом")

        p1, p2, p3 = st.columns(3)
        p1.metric("📈 Прибыль (Нал)", f"{int(cash_profit):,} сом")
        p2.metric("📈 Прибыль (Рассрочка)", f"{int(credit_profit):,} сом")
        p3.metric("🏆 Суммарная прибыль", f"{int(total_profit):,} сом")
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric("🟢 Наличные", f"{int(cash_turnover):,} сом")
        k2.metric("🔵 Рассрочки", f"{int(credit_turnover):,} сом")
        k3.metric("🛍️ Всего", f"{int(cash_turnover + credit_turnover):,} сом")

    # ===== ПОЛНЫЙ ОТЧЁТ (только Админ) =====
    if user_role == "Администратор":
        st.markdown("---")
        st.subheader("📋 Полный отчет по дням")

        daily_data = []
        current = start_date
        while current <= end_date:
            day_sales = filtered_df[filtered_df['day_obj'] == current]
            day_cash = day_sales[day_sales['payment'] == 'Наличные']
            day_credit = day_sales[day_sales['payment'] == 'Рассрочка']

            cash_sale = float(day_cash['total_sale'].sum()) if not day_cash.empty else 0
            credit_sale = float(day_credit['total_sale'].sum()) if not day_credit.empty else 0
            cash_p = float((day_cash['total_sale'] - day_cash['total_cost']).sum()) if not day_cash.empty else 0
            
            credit_p = 0
            if not day_credit.empty:
                for _, r in day_credit.iterrows():
                    cost = float(r.get("total_cost", 0) or 0)
                    down = float(r.get("down_payment", 0) or 0)
                    bal = float(r.get("credit_balance", 0) or 0)
                    credit_p += (down + bal) - cost

            day_products = [p for p in products_data if parse_day(p.get("date")) == current]
            qty_rec = sum(int(p.get("qty", 0) or 0) for p in day_products)
            cost_rec = sum(float(p.get("qty", 0) or 0) * float(p.get("cost", 0) or 0) for p in day_products)

            if cash_sale or credit_sale or qty_rec:
                daily_data.append({
                    "Дата": current.strftime("%Y-%m-%d"),
                    "Продажи наличкой": cash_sale,
                    "Продажи в рассрочку": credit_sale,
                    "Прибыль наличные": cash_p,
                    "Прибыль рассрочка": credit_p,
                    "Товаров на складе (шт)": qty_rec,
                    "Сумма товаров": cost_rec,
                    "Общая прибыль": cash_p + credit_p
                })
            current += timedelta(days=1)

        if daily_data:
            report_df = pd.DataFrame(daily_data)
            display = report_df.copy()
            for col in display.columns[1:]:
                display[col] = display[col].map("{:,.0f}".format)
            st.dataframe(display, use_container_width=True, hide_index=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                report_df.to_excel(writer, index=False, sheet_name="Полный отчет")
            buffer.seek(0)
            st.download_button("📥 Скачать Полный отчет", data=buffer,
                               file_name=f"Polnyy_otchet_{start_date}_{end_date}.xlsx",
                               use_container_width=True)

    # ===== СПИСОК ЧЕКОВ =====
    st.markdown("---")
    st.subheader("📋 Список оформленных чеков")

    report_display = []
    for _, row in filtered_df.iterrows():
        item = {
            "Дата": format_date_to_ddmmyyyy(row['date'], include_time=True),
            "Наименование": fix_contract_name_on_fly(row['name'], row['date']),
            "Кол-во": int(row['qty']),
            "Тип оплаты": row['payment'],
            "Сумма": int(row['total_sale']),
            "Закупка": int(row.get('total_cost', 0)),
            "Прибыль": int(row.get('profit', 0)),
            "sale_id": row['id'],
            "raw_payment": row['payment'],
            "down_payment": int(row.get('down_payment', 0) or 0)
        }
        report_display.append(item)

    df_display = pd.DataFrame(report_display)
    st.dataframe(df_display.drop(columns=["sale_id", "raw_payment", "down_payment"], errors="ignore"),
                 use_container_width=True, hide_index=True)

    # ===== РЕДАКТИРОВАНИЕ =====
    if user_role == "Администратор":
        st.markdown("---")
        st.subheader("✏️ Редактировать выбранную операцию")

        edit_options = {
            f"{row['Дата']} | {row['Наименование']} | {row['Сумма']} сом": row
            for _, row in df_display.iterrows()
        }
        selected_label = st.selectbox("Выберите операцию", ["-- Не выбрано --"] + list(edit_options.keys()))

        if selected_label != "-- Не выбрано --":
            selected = edit_options[selected_label]
            sale_id = selected["sale_id"]
            sale_data = supabase.table("sales").select("*").eq("id", sale_id).execute().data

            if sale_data:
                sale = sale_data[0]
                with st.form("edit_form"):
                    new_name = st.text_input("Наименование", value=str(sale.get("name", "")))
                    new_qty = st.number_input("Количество", min_value=0, value=int(sale.get("qty", 0)))
                    new_total_sale = st.number_input("Сумма продажи", min_value=0, value=int(sale.get("total_sale", 0)))
                    new_total_cost = st.number_input("Себестоимость (Закупка)", min_value=0, value=int(sale.get("total_cost", 0)))
                    
                    st.info(f"Прибыль будет: **{new_total_sale - new_total_cost:,} сом**")

                    col1, col2 = st.columns(2)
                    with col1:
                        new_payment = st.selectbox("Тип оплаты", ["Наличные", "Рассрочка"],
                                                   index=0 if sale.get("payment") == "Наличные" else 1)
                    with col2:
                        new_down = st.number_input("Перв. взнос", min_value=0, value=int(sale.get("down_payment", 0) or 0))
                    
                    new_balance = st.number_input("Остаток рассрочки", min_value=0, value=int(sale.get("credit_balance", 0) or 0))

                    if st.form_submit_button("💾 Сохранить изменения", type="primary"):
                        try:
                            supabase.table("sales").update({
                                "name": new_name.strip(),
                                "qty": new_qty,
                                "total_sale": new_total_sale,
                                "total_cost": new_total_cost,
                                "profit": new_total_sale - new_total_cost,
                                "payment": new_payment,
                                "down_payment": new_down,
                                "credit_balance": new_balance
                            }).eq("id", sale_id).execute()
                            st.success("✅ Сохранено!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # ===== ОТМЕНА =====
    if user_role == "Администратор":
        st.markdown("---")
        st.subheader("🗑️ Отменить (удалить) продажу")

        cancel_options = {
            f"{row['Дата']} | {row['Наименование']} | {row['Сумма']} сом": row
            for _, row in df_display.iterrows()
        }
        selected_cancel = st.selectbox("Выберите операцию для удаления", ["-- Не выбрано --"] + list(cancel_options.keys()), key="cancel_select")

        if selected_cancel != "-- Не выбрано --":
            s_del = cancel_options[selected_cancel]
            if st.button("🚨 БЕЗВОЗВРАТНО УДАЛИТЬ эту продажу", type="primary"):
                try:
                    # Возвращаем товар на склад (упрощённо)
                    if s_del["raw_payment"] == "Наличные":
                        # Пытаемся вернуть количество
                        pass  # можно доработать позже
                    
                    supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                    supabase.table("credit_payments").delete().eq("sale_id", s_del["sale_id"]).execute()
                    st.success("Продажа удалена!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка удаления: {e}")
