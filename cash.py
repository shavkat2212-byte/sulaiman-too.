import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    # 1. ЗАГРУЗКА ДАННЫХ ИЗ БАЗЫ (Твои родные работающие запросы)
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    # Считаем базовые переменные
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    
    paid_credits_res = supabase.table("credit_payments").select("amount_paid").execute()
    total_credit_collected = sum(float(p["amount_paid"]) for p in paid_credits_res.data)
    
    # Безопасный подсчет ручного потока кассы
    manual_cash_flow = 0.0
    if ops_res.data:
        for op in ops_res.data:
            # Ищем колонку с суммой, проверяя все возможные варианты имени
            val = op.get("amount") or op.get("Сумма") or list(op.values())[1] # берем значение, если имя отличается
            try: manual_cash_flow += float(val)
            except: pass

    # ИСПРАВЛЕННАЯ ИТОГОВАЯ ФОРМУЛА НАЛИЧНЫХ (Без удваивания взносов!)
    current_cash_in_hand = full_cash_sales + manual_cash_flow
    
    # Твои любимые верхние карточки
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", f"{credit_debts - total_credit_collected:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль", f"{sum(float(s['profit']) for s in sales_res.data):,.2f} сом")
    
    st.markdown("---")
    
    # ФОРМА ВНЕСЕНИЯ/ИЗЪЯТИЯ (Твоя родная рабочая форма)
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
        comment = st.text_input("Комментарий / Причина")
        
        if st.form_submit_button("Выполнить операцию"):
            actual = amount if "Положить" in op_type else -amount
            # Чтобы не зависеть от имени колонки, пишем и в amount, и в Сумма
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"), 
                "amount": actual, 
                "comment": comment or op_type
            }).execute()
            st.success("Операция проведена!")
            st.rerun()

    # --- РАЗДЕЛЕНИЕ НА ТАБЛИЦЫ ПРИХОДОВ И РАСХОДОВ ---
    st.markdown("---")
    
    if ops_res.data:
        df_ops = pd.DataFrame(ops_res.data)
        
        # Автоматически переименуем колонки для красивого вывода, если они есть
        df_ops = df_ops.rename(columns={
            "date": "Дата", "amount": "Сумма (сом)", "Сумма": "Сумма (сом)", 
            "comment": "Комментарий / Причина", "Комментарий": "Комментарий / Причина"
        }, errors="ignore")
        
        # Определяем имя колонки с суммами в получившемся датафрейме
        sum_col = "Сумма (сом)" if "Сумма (сом)" in df_ops.columns else df_ops.columns[1]
        
        # Принудительно приводим к числам для фильтрации
        df_ops[sum_col] = pd.to_numeric(df_ops[sum_col], errors='coerce').fillna(0)
        
        # ТАБЛИЦА 1: ПРИХОДЫ (Всё что больше 0)
        st.subheader("🟢 История кассовых приходов")
        df_income = df_ops[df_ops[sum_col] > 0]
        if not df_income.empty:
            st.dataframe(df_income, use_container_width=True, hide_index=True)
            st.markdown(f"**💰 ИТОГО ПРИХОДОВ: `{int(df_income[sum_col].sum()):,}` сом**")
        else:
            st.write("Приходов пока не зафиксировано.")
            
        st.markdown("---")
        
        # ТАБЛИЦА 2: РАСХОДЫ (Всё что меньше 0)
        st.subheader("🔴 История расходов из кассы")
        df_expense = df_ops[df_ops[sum_col] < 0].copy()
        if not df_expense.empty:
            # Показываем расходы красивыми положительными числами
            df_expense[sum_col] = df_expense[sum_col].abs()
            st.dataframe(df_expense, use_container_width=True, hide_index=True)
            st.markdown(f"**💸 ИТОГО РАСХОДОВ: `{int(df_expense[sum_col].sum()):,}` сом**")
        else:
            st.write("Расходов пока не зафиксировано.")
    else:
        st.write("История кассовых движений пуста.")
