# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 2.6 (Улучшенная таблица остатка по дням)

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

    # ==================== УЛУЧШЕННЫЙ РАСЧЁТ ПО ДНЯМ ====================
    all_ops = []

    # Наличные продажи
    for s in sales_data:
        if s.get("payment") == "Наличные":
            all_ops.append({
                "day": s.get("day")[:10] if s.get("day") else None,
                "cash_sales": float(s.get("total_sale", 0)),
                "inflow": 0,
                "outflow": 0
            })

    # Операции из cash_operations
    for op in ops_data:
        amount = float(op.get("amount", 0))
        all_ops.append({
            "day": op.get("date")[:10] if op.get("date") else None,
            "cash_sales": 0,
            "inflow": amount if amount > 0 else 0,
            "outflow": -amount if amount < 0 else 0
        })

    if all_ops:
        df_all = pd.DataFrame(all_ops)
        df_all = df_all[df_all['day'].notna()]
        
        daily = df_all.groupby('day').sum().reset_index().sort_values('day')
        
        # Кумулятивный остаток
        daily['balance'] = daily['cash_sales'] + daily['inflow'] + daily['outflow']
        daily['balance'] = daily['balance'].cumsum()
        
        # Сдвиг для остатка на начало дня
        daily['balance_start'] = daily['balance'].shift(1, fill_value=0)
        
        # Красивая таблица
        daily_display = daily.copy()
        daily_display = daily_display.rename(columns={
            'day': 'Дата',
            'cash_sales': 'Продажи наличкой',
            'inflow': 'Приходы (взносы, платежи)',
            'outflow': 'Расходы / Изъятия',
            'balance_start': 'Остаток на начало дня',
            'balance': 'Остаток на конец дня'
        })
        
        # Форматирование чисел
        for col in ['Продажи наличкой', 'Приходы (взносы, платежи)', 'Расходы / Изъятия', 'Остаток на начало дня', 'Остаток на конец дня']:
            daily_display[col] = daily_display[col].map('{:,.0f}'.format)
        
        st.dataframe(daily_display, use_container_width=True, hide_index=True)
    else:
        st.info("Пока нет операций.")
    # =====================================================================

    st.markdown("---")
    st.subheader("📜 История операций")

    # (фильтр, таблица, удаление, новая операция — как было раньше)
    # Чтобы не делать сообщение слишком длинным, оставь как в предыдущей версии. Если нужно — скажи, дам полный код.

    # Новая операция (только расходы)
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
