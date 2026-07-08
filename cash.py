import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def format_time_on_screen(date_str):
    """Красивое отображение даты/времени"""
    if not date_str: return "-"
    return str(date_str).replace(".2026", ".26")

def show_cash_page():
    # Проверка роли пользователя
    current_user = st.session_state.get("user", {})
    user_role = current_user.get("role", "Кассир")
    
    if user_role == "Администратор":
        st.header("💵 Управление кассой (Панель Администратора)")
    else:
        st.header("💵 Оперативная касса (Панель Кассира)")

    # 1. Загрузка данных из БД за всё время
    sales_res = supabase.table("sales").select("total_sale, payment, down_payment, day, profit").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    # Чтобы не падало из-за структуры, берем только существующую колонку amount_paid
    payments_res = supabase.table("credit_payments").select("amount_paid").execute()
    
    # Загружаем выплаты поставщикам, если таблица существует
    try: suppliers_res = supabase.table("supplier_payments").select("amount").execute()
    except: suppliers_res = type('obj', (object,), {'data': []})

    # --- МАТЕМАТИКА 1: ТОЧНЫЙ ОСТАТОК НАЛИЧНЫХ «ЗДЕСЬ И СЕЙЧАС» ---
    # Прямые наличные продажи
    all_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    
    # Так как при рассрочке первоначальный взнос дублируется в cash_operations в sales.py,
    # мы НЕ плюсуем сюда s["down_payment"], иначе сумма удваивается. 
    # Все взносы и ручные расходы идеально считываются напрямую из cash_operations!
    all_manual_and_downpayments = sum(float(op['amount']) for op in ops_res.data)
    
    # Фактически принятые оплаты долей по рассрочкам из календаря платежей
    all_collected_credits = sum(float(p.get("amount_paid", 0.0) or 0) for p in payments_res.data)
    
    # Выплаты поставщикам
    all_supplier_flow = sum(float(sup['amount']) for sup in suppliers_res.data)

    # Итоговый чистый баланс в кассе
    net_cash_in_hand = all_cash_sales + all_manual_and_downpayments + all_collected_credits - all_supplier_flow

    # --- МАТЕМАТИКА 2: ОПЕРАТИВНЫЕ ИТОГИ СТРОГО ЗА СЕГОДНЯ ---
    today_str_dash = datetime.now().strftime("%Y-%m-%d")
    today_str_dot = datetime.now().strftime("%d.%m.%Y")

    # Прямые продажи за сегодня (Наличные)
    today_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные" and str(s.get("day")) == today_str_dash)
    
    # Первоначальные взносы, внесенные СЕГОДНЯ (фильтруем по дате из cash_operations)
    today_ops = [op for op in ops_res.data if str(op.get("date", "")).startswith(today_str_dash) or str(op.get("date", "")).startswith(today_str_dot)]
    
    today_down_payments = sum(float(op['amount']) for op in today_ops if "Перв. взнос" in str(op.get("comment", "")))
    today_manual_in = sum(float(op['amount']) for op in today_ops if float(op['amount']) > 0 and "Перв. взнос" not in str(op.get("comment", "")))
    today_expenses = sum(abs(float(op['amount'])) for op in today_ops if float(op['amount']) < 0)

    # ВЫВОД КЛЮЧЕВЫХ МЕТРИК
    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric("💰 Фактический остаток наличных в кассе", f"{int(net_cash_in_hand):,} сом")
    
    if user_role == "Администратор":
        all_profit = sum(float(s.get('profit', 0.0) or 0) for s in sales_res.data)
        c2.metric("📈 Общая чистая прибыль бизнеса", f"{int(all_profit):,} сом")
    else:
        # Для кассира выводим дневную выручку
        today_revenue = today_cash_sales + today_down_payments
        c2.metric("🛍️ Дневная выручка от продаж", f"{int(today_revenue):,} сом")

    # СЕКЦИЯ ДЛЯ КАССИРА: ЧТО ПРОИСХОДИЛО СЕГОДНЯ
    st.markdown("---")
    st.subheader("📋 Движение наличных за сегодняшний день")
    
    col_day1, col_day2, col_day3, col_day4 = st.columns(4)
    col_day1.metric("🟢 Прямые продажи (Нал)", f"{int(today_cash_sales):,} сом")
    col_day2.metric("📥 Перв. взносы (Рассрочка)", f"{int(today_down_payments):,} сом")
    col_day3.metric("➕ Прочие приходы/Сдача", f"{int(today_manual_in):,} сом")
    col_day4.metric("🔴 Выдачи / Расходы / Инкассация", f"{int(today_expenses):,} сом")

    # ФОРМА ИЗЪЯТИЯ (Только для Администратора)
    if user_role == "Администратор":
        st.markdown("---")
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
        st.markdown("---")
        st.info("ℹ️ Проводить инкассацию и ручное изъятие/внесение средств может только Администратор.")

    # ИСТОРИЯ ОПЕРАЦИЙ (Видят все)
    st.subheader("📜 История кассовых операций")
    if ops_res.data:
        df_ops = pd.DataFrame(ops_res.data)
        display_rows = []
        for _, row in df_ops.iterrows():
            amt = float(row['amount'])
            display_rows.append({
                "Дата операции": format_time_on_screen(row['date']),
                "Движение": "🟢 ПРИХОД" if amt > 0 else "🔴 РАСХОД",
                "Сумма (сом)": int(abs(amt)),
                "Комментарий / Причина": row['comment']
            })
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
    else:
        st.write("История ручных операций пуста.")
