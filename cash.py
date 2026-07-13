# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 2.5 (Полная версия: остаток по дням + история операций + удаление)

import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    user_role = st.session_state.get("user", {}).get("role", "Кассир")

    try:
        sales_res = supabase.table("sales").select("*").execute()
        ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    except Exception as e:
        st.error(f"Ошибка подключения к базе: {e}")
        return

    sales_data = sales_res.data if sales_res.data else []
    ops_data = ops_res.data if ops_res.data else []

    # ==================== ОСНОВНЫЕ МЕТРИКИ ====================
    full_cash_sales = sum(float(s["total_sale"]) for s in sales_data if s.get("payment") == "Наличные")
    manual_cash_flow = sum(float(op.get('amount', 0)) for op in ops_data)
    current_cash_in_hand = full_cash_sales + manual_cash_flow

    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе (сейчас)", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", 
              f"{sum(float(s.get('credit_balance', 0)) for s in sales_data if s.get('payment') == 'Рассрочка'):,} сом")
    c3.metric("📈 Чистая прибыль (всего)", 
              f"{sum(float(s.get('profit', 0)) for s in sales_data):,.2f} сом")

    st.markdown("---")
    st.subheader("📊 Остаток кассы по дням")

    # ==================== ОСТАТОК ПО ДНЯМ ====================
    all_ops = []
    for s in sales_data:
        if s.get("payment") == "Наличные":
            all_ops.append({"day": s.get("day")[:10] if s.get("day") else None, "amount": float(s.get("total_sale", 0))})
    for op in ops_data:
        all_ops.append({"day": op.get("date")[:10] if op.get("date") else None, "amount": float(op.get("amount", 0))})

    if all_ops:
        df_all = pd.DataFrame(all_ops)
        df_all = df_all[df_all['day'].notna()]
        daily = df_all.groupby('day')['amount'].sum().reset_index().sort_values('day')
        daily['balance'] = daily['amount'].cumsum()

        daily_display = daily.copy()
        daily_display['amount'] = daily_display['amount'].map('{:,.0f}'.format)
        daily_display['balance'] = daily_display['balance'].map('{:,.0f}'.format)
        daily_display = daily_display.rename(columns={'day': 'Дата', 'amount': 'Приход/Расход за день', 'balance': 'Остаток на конец дня'})
        st.dataframe(daily_display, use_container_width=True, hide_index=True)
    else:
        st.info("Пока нет операций.")

    st.markdown("---")
    st.subheader("📜 История кассовых операций")

    # Фильтр по датам
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        start_date = st.date_input("Начало периода", value=datetime.now().date() - timedelta(days=30))
    with col_f2:
        end_date = st.date_input("Конец периода", value=datetime.now().date())

    df_ops = pd.DataFrame(ops_data) if ops_data else pd.DataFrame()
    if not df_ops.empty:
        try:
            df_ops['date_obj'] = pd.to_datetime(df_ops['date'].astype(str).str[:10], format='%Y-%m-%d', errors='coerce').dt.date
            filtered_ops = df_ops[(df_ops['date_obj'] >= start_date) & (df_ops['date_obj'] <= end_date)].copy()
        except:
            filtered_ops = df_ops
    else:
        filtered_ops = pd.DataFrame()

    if not filtered_ops.empty:
        display_df = filtered_ops[["id", "date", "amount", "comment", "created_at"]].copy()
        display_df["amount"] = display_df["amount"].map('{:,.0f}'.format)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Операций за выбранный период нет.")

    # ==================== УДАЛЕНИЕ (только Админ) ====================
    if user_role == "Администратор" and not filtered_ops.empty:
        st.markdown("---")
        st.subheader("🗑️ Удалить операцию (только Администратор)")

        with st.form("delete_form"):
            options = {f"{row['id']} | {row['date']} | {int(row['amount']):,} сом | {row.get('comment', '')}": row['id'] for _, row in filtered_ops.iterrows()}
            selected_label = st.selectbox("Выберите операцию", list(options.keys()))
            selected_id = options[selected_label]
            confirm = st.checkbox("Подтверждаю удаление")

            if st.form_submit_button("Удалить операцию", type="primary"):
                if confirm:
                    supabase.table("cash_operations").delete().eq("id", selected_id).execute()
                    st.success("Операция удалена!")
                    st.rerun()
                else:
                    st.warning("Поставьте галочку подтверждения")

    # ==================== НОВАЯ ОПЕРАЦИЯ ====================
    st.markdown("---")
    st.subheader("📤 Новая операция (только расходы / изъятия)")

    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип расхода", [
            "Взять деньги (Инкассация / Личные нужды)",
            "Выплата за товар (Поставщику)"
        ])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=1000.0, step=100.0)
        comment = st.text_input("Комментарий / Причина", value=op_type)

        if st.form_submit_button("Списать из кассы", type="primary"):
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "amount": -amount,
                "comment": comment or op_type
            }).execute()
            st.success("✅ Расход зафиксирован!")
            st.rerun()
