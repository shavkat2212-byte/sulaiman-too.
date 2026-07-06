# Магазин «Сулайман-Тоо» — Модуль: Состояние кассы магазина
# Версия программы: 1.5.2 (Внедрен фильтр по ролям, точный расчет наличных и итоги дня)

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def format_time_on_screen(date_str):
    """Красивое отображение даты/времени"""
    if not date_str: return "-"
    return str(date_str).replace(".2026", ".26") # для компактности

def show_cash_page():
    # Проверка роли пользователя
    current_user = st.session_state.get("user", {})
    user_role = current_user.get("role", "Кассир")
    
    if user_role == "Администратор":
        st.header("💵 Управление кассой (Панель Администратора)")
    else:
        st.header("💵 Оперативная касса (Панель Кассира)")

    # 1. Загрузка данных из БД за всё время для точного баланса «Здесь и сейчас»
    sales_res = supabase.table("sales").select("total_sale, payment, down_payment, day").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    payments_res = supabase.table("credit_payments").select("amount_paid, created_at").execute()
    
    # Также загружаем выплаты поставщикам (они ведь тоже уменьшают наличные в кассе!)
    try: suppliers_res = supabase.table("supplier_payments").select("amount, date").execute()
    except: suppliers_res = type('obj', (object,), {'data': []})

    # --- МАТЕМАТИКА 1: ФАКТИЧЕСКИЙ ОСТАТОК НАЛИЧНЫХ ВСЕГО ---
    # Прямые наличные продажи за все время
    all_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    # Первоначальные взносы по рассрочкам за все время
    all_down_payments = sum(float(s.get("down_payment", 0.0) or 0) for s in sales_res.data if s.get("payment") == "Рассрочка")
    # Фактически принятые платежи по рассрочкам (оплата долей/долгов)
    all_collected_credits = sum(float(p.get("amount_paid", 0.0) or 0) for p in payments_res.data)
    # Ручной поток (Внесения [+] / Изъятия [-])
    all_manual_flow = sum(float(op['amount']) for op in ops_res.data)
    # Выплаты контрагентам/поставщикам [-]
    all_supplier_flow = sum(float(sup['amount']) for sup in suppliers_res.data)

    # Итоговый точный остаток денег в сейфе/кассе прямо сейчас:
    net_cash_in_hand = all_cash_sales + all_down_payments + all_collected_credits + all_manual_flow - all_supplier_flow

    # --- МАТЕМАТИКА 2: ПОКАЗАТЕЛИ СТРОГО ЗА СЕГОДНЯ ---
    today_str_dash = datetime.now().strftime("%Y-%m-%d") # Формат YYYY-MM-DD
    today_str_dot = datetime.now().strftime("%d.%m.%Y")   # Формат DD.MM.YYYY

    today_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные" and str(s.get("day")) == today_str_dash)
    today_down_payments = sum(float(s.get("down_payment", 0.0) or 0) for s in sales_res.data if s.get("payment") == "Рассрочка" and str(s.get("day")) == today_str_dash)
    
    # Сегодняшние ручные расходы/приходы
    today_manual_ops = [op for op in ops_res.data if str(op.get("date", "")).startswith(today_str_dash) or str(op.get("date", "")).startswith(today_str_dot)]
    today_manual_inout = sum(float(op['amount']) for op in today_manual_ops)

    # ВЫВОД КЛЮЧЕВЫХ МЕТРИК
    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric("💰 Фактически в кассе (Остаток наличных)", f"{int(net_cash_in_hand):,} сом")
    
    if user_role == "Администратор":
        # Администратор видит чистую прибыль бизнеса
        all_profit = sum(float(s.get('profit', 0.0) or 0) for s in sales_res.data)
        c2.metric("📈 Общая чистая прибыль бизнеса", f"{int(all_profit):,} сом")
    else:
        # Кассир видит общую сумму продаж (выручку) за сегодняшний день
        today_total_revenue = today_cash_sales + today_down_payments
        c2.metric("🛍️ Выручка от продаж за сегодня", f"{int(today_total_revenue):,} сом")

    # СЕКЦИЯ: ИТОГИ ДНЯ ДЛЯ КАССИРА
    st.markdown("---")
    st.subheader("📋 Оперативные итоги за сегодня")
    col_day1, col_day2, col_day3 = st.columns(3)
    col_day1.markdown(f"**Прямые продажи (Нал):** {int(today_cash_sales):,} сом")
    col_day2.markdown(f"**Перв. взносы по рассрочкам:** {int(today_down_payments):,} сом")
    
    # Считаем отдельно расходы (минусовые операции) за сегодня
    today_expenses = sum(abs(float(op['amount'])) for op in today_manual_ops if float(op['amount']) < 0)
    col_day3.markdown(f"**Расход/Инкассация сегодня:** {int(today_expenses):,} сом")

    # БЛОК ВНЕСЕНИЯ И ИЗЪЯТИЯ ДЕНЕГ (Только для Администратора)
    st.markdown("---")
    if user_role == "Администратор":
        st.subheader("📥 / 📤 Внести или взять деньги из кассы")
        with st.form("cash_op_form", clear_on_submit=True):
            op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
            amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
            comment = st.text_input("Комментарий / Причина")
            
            if st.form_submit_button("Выполнить операцию"):
                actual = amount if "Положить" in op_type else -amount
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                supabase.table("cash_operations").insert({
                    "date": now_str, 
                    "amount": actual, 
                    "comment": comment or op_type
                }).execute()
                st.success("🎉 Операция успешно проведена!")
                st.rerun()
    else:
        st.info("ℹ️ Права на ручное внесение и изъятие (инкассацию) наличных денег есть только у Администратора.")

    # СЕКЦИЯ: ИСТОРИЯ ДВИЖЕНИЯ КАССЫ
    st.markdown("---")
    st.subheader("📜 История кассовых операций (Хронология)")
    
    if ops_res.data:
        df_ops = pd.DataFrame(ops_res.data)
        
        # Красивое распределение на Приход / Расход для таблицы
        display_rows = []
        for _, row in df_ops.iterrows():
            amt = float(row['amount'])
            display_rows.append({
                "Дата операции": format_time_on_screen(row['date']),
                "Тип": "🟢 ПРИХОД (Пополнение)" if amt > 0 else "🔴 РАСХОД (Изъятие)",
                "Сумма (сом)": int(abs(amt)),
                "Комментарий / Причина": row['comment']
            })
            
        df_display = pd.DataFrame(display_rows)
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.write("История ручных кассовых операций пуста.")
