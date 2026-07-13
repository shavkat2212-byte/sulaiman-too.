# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 2.4 (Исправлен расчёт остатка по дням — теперь совпадает с текущим)

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

    # ==================== ИСПРАВЛЕННЫЙ РАСЧЁТ ОСТАТКА ПО ДНЯМ ====================
    all_ops = []

    # Добавляем наличные продажи
    for s in sales_data:
        if s.get("payment") == "Наличные":
            all_ops.append({
                "day": s.get("day")[:10] if s.get("day") else None,
                "amount": float(s.get("total_sale", 0))
            })

    # Добавляем все операции из cash_operations (взносы, расходы, выплаты)
    for op in ops_data:
        all_ops.append({
            "day": op.get("date")[:10] if op.get("date") else None,
            "amount": float(op.get("amount", 0))
        })

    if all_ops:
        df_all = pd.DataFrame(all_ops)
        df_all = df_all[df_all['day'].notna()]
        
        # Группируем по дням и считаем приход/расход
        daily = df_all.groupby('day')['amount'].sum().reset_index()
        daily = daily.sort_values('day')
        
        # Считаем кумулятивный остаток
        daily['balance'] = daily['amount'].cumsum()
        
        # Красивая таблица
        daily_display = daily.copy()
        daily_display['amount'] = daily_display['amount'].map('{:,.0f}'.format)
        daily_display['balance'] = daily_display['balance'].map('{:,.0f}'.format)
        daily_display = daily_display.rename(columns={
            'day': 'Дата',
            'amount': 'Приход/Расход за день',
            'balance': 'Остаток на конец дня'
        })
        
        st.dataframe(daily_display, use_container_width=True, hide_index=True)
        
        # Проверка совпадения
        last_balance = daily['balance'].iloc[-1] if not daily.empty else 0
        st.info(f"Последний остаток в таблице: **{last_balance:,.0f} сом** | Текущий остаток: **{current_cash_in_hand:,.0f} сом**")
    else:
        st.info("Пока нет операций.")
    # =====================================================================

    st.markdown("---")
    st.subheader("📜 История операций")

    # (остальной код истории, фильтра, новой операции — оставляем как было в предыдущей версии)
    # Чтобы не делать сообщение слишком длинным, я могу добавить его, если нужно. Пока оставь как было.

    # Новая операция
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
