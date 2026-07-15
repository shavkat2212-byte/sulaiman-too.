# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 2.7 (Исправлен расчёт остатка по дням)

import streamlit as st
import pandas as pd
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

    # ==================== ПРАВИЛЬНЫЙ РАСЧЁТ ПО ДНЯМ ====================
    all_ops = []

    # 1. Наличные продажи
    for s in sales_data:
        if s.get("payment") == "Наличные":
            day = str(s.get("day", ""))[:10]
            if day:
                all_ops.append({
                    "day": day,
                    "cash_sales": float(s.get("total_sale", 0)),
                    "inflow": 0.0,
                    "outflow": 0.0
                })

    # 2. Операции из cash_operations
    for op in ops_data:
        day = str(op.get("date", ""))[:10]
        if not day:
            continue
        amount = float(op.get("amount", 0))
        all_ops.append({
            "day": day,
            "cash_sales": 0.0,
            "inflow": amount if amount > 0 else 0.0,
            "outflow": -amount if amount < 0 else 0.0   # делаем положительным для отображения
        })

    if all_ops:
        df_all = pd.DataFrame(all_ops)
        
        # Группируем по дням
        daily = df_all.groupby('day').agg({
            'cash_sales': 'sum',
            'inflow': 'sum',
            'outflow': 'sum'
        }).reset_index().sort_values('day')

        # Чистый результат за день
        daily['net'] = daily['cash_sales'] + daily['inflow'] - daily['outflow']
        
        # Остаток на конец дня (кумулятивный)
        daily['balance_end'] = daily['net'].cumsum()
        
        # Остаток на начало дня = предыдущий конец дня
        daily['balance_start'] = daily['balance_end'].shift(1).fillna(0)

        # Красивая таблица
        display = daily[['day', 'balance_start', 'cash_sales', 'inflow', 'outflow', 'balance_end']].copy()
        display.columns = [
            'Дата',
            'Остаток на начало дня',
            'Продажи наличкой',
            'Приходы (взносы, платежи)',
            'Расходы / Изъятия',
            'Остаток на конец дня'
        ]

        # Форматирование
        for col in display.columns[1:]:
            display[col] = display[col].map('{:,.0f}'.format)

        st.dataframe(display, use_container_width=True, hide_index=True)

        # Проверка
        last_end = daily['balance_end'].iloc[-1]
        st.caption(f"Последний остаток в таблице: **{last_end:,.0f} сом** | Текущий остаток кассы: **{current_cash_in_hand:,.0f} сом**")
    else:
        st.info("Пока нет операций для расчёта.")

    # ==================== ИСТОРИЯ ОПЕРАЦИЙ ====================
    st.markdown("---")
    st.subheader("📜 История кассовых операций")

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

    # ==================== УДАЛЕНИЕ (Админ) ====================
    if user_role == "Администратор" and not filtered_ops.empty:
        st.markdown("---")
        st.subheader("🗑️ Удалить операцию (только Администратор)")

        with st.form("delete_form"):
            options = {
                f"{row['id']} | {row['date']} | {int(row['amount']):,} сом | {row.get('comment', '')}": row['id']
                for _, row in filtered_ops.iterrows()
            }
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
