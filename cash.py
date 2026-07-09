# Магазин «Сулайман-Тоо» — Модуль: Состояние кассы
# Версия программы: 1.9.5 (Финальное исправление по hint базы данных, колонки приходов и расходов)

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    # 1. ЗАГРУЗКА ДАННЫХ ИЗ БАЗЫ (Твои рабочие запросы)
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance, day, name").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    payments_res = supabase.table("credit_payments").select("amount_paid, updated_at, client_id").execute()
    
    clients_raw = supabase.table("clients").select("id, fio").execute()
    clients_dict = {c["id"]: c["fio"] for c in clients_raw.data} if clients_raw.data else {}

    # --- МАТЕМАТИКА ВЕРХНИХ КАРТОЧЕК (Без удваивания взносов) ---
    full_cash_sales = sum(s.get("total_sale", 0) for s in sales_res.data if s.get("payment") == "Наличные")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    total_credit_collected = sum(float(p.get("amount_paid", 0.0)) for p in payments_res.data)
    
    # Считаем ручной поток из cash_operations (где уже лежат все взносы)
    manual_cash_flow = sum(float(op.get('amount', 0.0)) for op in ops_res.data)
    
    # ПРАВИЛЬНАЯ ИТОГОВАЯ ФОРМУЛА: Убран взнос из sales, чтобы сумма не удваивалась
    current_cash_in_hand = full_cash_sales + manual_cash_flow
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", f"{credit_debts - total_credit_collected:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль", f"{sum(float(s.get('profit', 0.0)) for s in sales_res.data):,.2f} сом")
    
    st.markdown("---")
    
    # ФОРМА ВНЕСЕНИЯ/ИЗЪЯТИЯ ДЕНЕГ
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", ["Взять деньги (Инкассация/Личные нужды)", "Положить деньги (Пополнение кассы/Сдача)"])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0)
        comment = st.text_input("Комментарий / Причина")
        
        if st.form_submit_button("Выполнить операцию"):
            actual = amount if "Положить" in op_type else -amount
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"), 
                "amount": actual, 
                "comment": comment or op_type
            }).execute()
            st.success("Операция проведена!")
            st.rerun()

    # --- РАЗДЕЛЬНЫЙ КАЛЕНДАРНЫЙ ФИЛЬТР (Железная защита от перезапусков Стримлита) ---
    st.markdown("---")
    st.subheader("🔍 Выберите период для просмотра приходов и расходов кассы")
    col_d1, col_d2 = st.columns(2)
    start_date = col_d1.date_input("С даты", value=datetime.now().date(), key="c_start")
    end_date = col_d2.date_input("По дату", value=datetime.now().date(), key="c_end")

    # Списки для таблиц
    income_records = []
    expense_records = []

    # 1. Наличные продажи из sales
    for s in sales_res.data:
        if s.get("payment") == "Наличные" and s.get("day"):
            try: d_obj = datetime.strptime(s["day"], "%Y-%m-%d").date()
            except: continue
            if start_date <= d_obj <= end_date:
                income_records.append({
                    "Дата": s["day"], "Сумма (сом)": int(s.get("total_sale", 0)), "Описание / Причина": f"Наличная продажа: {s.get('name', '')}"
                })

    # 2. Оплаты рассрочек из credit_payments (По ПРАВИЛЬНОЙ колонке updated_at!)
    for p in payments_res.data:
        p_amt = float(p.get("amount_paid", 0) or 0)
        p_date = p.get("updated_at") or ""
        if p_amt > 0 and p_date:
            try: d_obj = datetime.strptime(p_date[:10], "%Y-%m-%d").date()
            except: continue
            if start_date <= d_obj <= end_date:
                client_name = clients_dict.get(p.get("client_id"), "Клиент")
                income_records.append({
                    "Дата": p_date[:16].replace("T", " "), "Сумма (сом)": int(p_amt), "Описание / Причина": f"Погашение рассрочки от {client_name}"
                })

    # 3. Ручные движения и взносы из cash_operations
    for op in ops_res.data:
        op_date = op.get("date") or ""
        if not op_date: continue
        try: d_obj = datetime.strptime(op_date[:10], "%Y-%m-%d").date()
        except: continue
        
        if start_date <= d_obj <= end_date:
            amt = float(op.get('amount', 0.0))
            comm = op.get('comment') or "-"
            if amt > 0:
                income_records.append({"Дата": op_date, "Сумма (сом)": int(amt), "Описание / Причина": comm})
            elif amt < 0:
                expense_records.append({"Дата": op_date, "Сумма (сом)": int(abs(amt)), "Описание / Причина": comm})

    # --- ВЫВОД ТАБЛИЦЫ ПРИХОДОВ ---
    st.markdown("---")
    st.subheader("🟢 История кассовых приходов")
    if income_records:
        df_inc = pd.DataFrame(income_records).sort_values(by="Дата", ascending=False)
        st.dataframe(df_inc, use_container_width=True, hide_index=True)
        st.markdown(f"**💰 ИТОГО ВСЕХ ПРИХОДОВ ЗА ПЕРИОД: `{df_inc['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Приходов за этот период нет.")

    # --- ВЫВОД ТАБЛИЦЫ РАСХОДОВ ---
    st.markdown("---")
    st.subheader("🔴 История расходов из кассы")
    if expense_records:
        df_exp = pd.DataFrame(expense_records).sort_values(by="Дата", ascending=False)
        st.dataframe(df_exp, use_container_width=True, hide_index=True)
        st.markdown(f"**💸 ИТОГО ВСЕХ РАСХОДОВ ЗА ПЕРИОД: `{df_exp['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Расходов за этот период нет.")
