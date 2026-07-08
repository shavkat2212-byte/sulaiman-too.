# Магазин «Сулайман-Тоо» — Модуль: Состояние кассы
# Версия программы: 1.8.5 (Полное исправление KeyError 'id', таблицы приходов/расходов, итоги за период)

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    # 1. ЗАГРУЗКА ДАННЫХ ИЗ БАЗЫ
    sales_res = supabase.table("sales").select("total_sale, profit, payment, down_payment, credit_balance, day").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    payments_res = supabase.table("credit_payments").select("amount_paid, payment_date, client_id").execute()
    
    try: suppliers_res = supabase.table("supplier_payments").select("*").execute()
    except: suppliers_res = type('obj', (object,), {'data': []})

    clients_raw = supabase.table("clients").select("id, fio").execute()
    clients_dict = {c["id"]: c["fio"] for c in clients_raw.data} if clients_raw.data else {}

    # --- МАТЕМАТИКА ВЕРХНИХ КАРТОЧЕК ---
    full_cash_sales = sum(s["total_sale"] for s in sales_res.data if s.get("payment") == "Наличные")
    credit_debts = sum(float(s.get("credit_balance", 0.0)) for s in sales_res.data if s.get("payment") == "Рассрочка")
    total_credit_collected = sum(float(p["amount_paid"] or 0) for p in payments_res.data)
    
    # Весь ручной поток кассы
    manual_cash_flow = sum(float(op.get('amount') or 0) for op in ops_res.data)
    
    # Выплаты поставщикам
    total_suppliers_paid = sum(float(sup.get('amount') or 0) for sup in suppliers_res.data)
    
    # Чистый остаток (Без удваивания взносов!)
    current_cash_in_hand = full_cash_sales + manual_cash_flow - total_suppliers_paid
    
    # Вывод верхних карточек
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", f"{credit_debts - total_credit_collected:,.2f} сом")
    c3.metric("📈 Всего чистая прибыль", f"{sum(float(s['profit'] or 0) for s in sales_res.data):,.2f} сом")
    
    st.markdown("---")
    
    # --- ВВОД НОВОЙ ОПЕРАЦИИ В КАССУ ---
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
            st.success("Операция успешно проведена!")
            st.rerun()

    st.markdown("---")
    
    # --- ФИЛЬТР ПО ПЕРИОДАМ ДЛЯ ОБЕИХ ТАБЛИЦ ---
    st.subheader("🔍 Выберите период отображения истории кассы")
    today_date = datetime.now().date()
    date_range = st.date_input("Диапазон дат истории", value=(today_date, today_date))
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = today_date, today_date

    # --- СБОР ДАННЫХ ДЛЯ ДВУХ ТАБЛИЦ ---
    income_records = []  # Приходы
    expense_records = [] # Расходы

    # 1. Прямой Нал из продаж
    for s in sales_res.data:
        if s.get("payment") == "Наличные" and s.get("day"):
            try: d_obj = datetime.strptime(s["day"], "%Y-%m-%d").date()
            except: d_obj = today_date
            
            if start_date <= d_obj <= end_date:
                income_records.append({
                    "Дата": s["day"], "Сумма (сом)": int(s["total_sale"]), "Комментарий / Причина": "Прямая наличная продажа"
                })

    # 2. Из cash_operations (Ручные приходы, взносы и расходы)
    for op in ops_res.data:
        op_date = str(op.get('date') or "")
        try: d_obj = datetime.strptime(op_date[:10], "%Y-%m-%d").date()
        except:
            try: d_obj = datetime.strptime(op_date[:10], "%d.%m.%Y").date()
            except: d_obj = today_date
            
        if start_date <= d_obj <= end_date:
            amt = float(op.get('amount') or 0)
            item = {"Дата": op_date, "Сумма (сом)": int(abs(amt)), "Комментарий / Причина": op.get('comment') or "-"}
            if amt > 0:
                income_records.append(item)
            else:
                expense_records.append(item)

    # 3. Из credit_payments (Оплаты долей клиентов)
    for p in payments_res.data:
        p_amt = float(p.get("amount_paid") or 0)
        p_date = p.get("payment_date") or ""
        if p_amt > 0 and p_date:
            try: d_obj = datetime.strptime(p_date[:10], "%d.%m.%Y").date()
            except: d_obj = today_date
            
            if start_date <= d_obj <= end_date:
                client_name = clients_dict.get(p.get("client_id"), "Клиент")
                income_records.append({
                    "Дата": p_date, "Сумma (сом)": int(p_amt), "Комментарий / Причина": f"Погашение рассрочки от {client_name}"
                })

    # 4. Из supplier_payments (Выплаты поставщикам)
    for sup in suppliers_res.data:
        sup_date = sup.get("date") or ""
        try: d_obj = datetime.strptime(sup_date[:10], "%d.%m.%Y").date()
        except: d_obj = today_date
        
        if start_date <= d_obj <= end_date:
            expense_records.append({
                "Дата": sup_date, "Сумма (сом)": int(float(sup.get('amount') or 0)), 
                "Комментарий / Причина": f"Выплата поставщику {sup.get('supplier')}: {sup.get('comment', '')}"
            })

    # --- ТАБЛИЦА 1: ПРИХОДЫ ---
    st.subheader("🟢 История кассовых приходов")
    if income_records:
        df_inc = pd.DataFrame(income_records)
        st.dataframe(df_inc, use_container_width=True, hide_index=True)
        st.markdown(f"**💰 ИТОГО ПРИХОДОВ ЗА ПЕРИОД: `{df_inc['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Приходов за этот период не найдено.")

    st.markdown("---")

    # --- ТАБЛИЦА 2: РАСХОДЫ ---
    st.subheader("🔴 История расходов из кассы")
    if expense_records:
        df_exp = pd.DataFrame(expense_records)
        st.dataframe(df_exp, use_container_width=True, hide_index=True)
        st.markdown(f"**💸 ИТОГО РАСХОДОВ ЗА ПЕРИОД: `{df_exp['Сумма (сом)'].sum():,}` сом**")
    else:
        st.write("Расходов за этот период не найдено.")

    # --- БЛОК БЕЗОПАСНОГО УДАЛЕНИЯ ОПЕРАЦИЙ (БЕЗ ИСПОЛЬЗОВАНИЯ ID) ---
    st.markdown("---")
    st.subheader("⚙️ Редактирование кассы (Удаление записей)")
    
    if ops_res.data:
        delete_options = {}
        for op in ops_res.data:
            op_date = op.get("date")
            op_comment = op.get("comment") or ""
            amt = float(op.get('amount') or 0)
            sign = "Приход" if amt > 0 else "Расход"
            
            # Строим уникальный текстовый ключ для селектбокса
            label = f"{op_date} | {sign} {int(abs(amt))} сом | Описание: {op_comment}"
            # Сохраняем связку даты и комментария для точечного удаления
            delete_options[label] = {"date": op_date, "comment": op_comment}
            
        selected_op_label = st.selectbox("🚨 Выберите ошибочную ручную операцию для удаления:", ["-- Не выбрано --"] + list(delete_options.keys()))
        
        if selected_op_label != "-- Не выбрано --":
            target = delete_options[selected_op_label]
            if st.button("❌ Безвозвратно удалить эту операцию из истории", type="primary", use_container_width=True):
                try:
                    # Удаляем точечно по совпадению даты и комментария
                    supabase.table("cash_operations").delete().eq("date", target["date"]).eq("comment", target["comment"]).execute()
                    st.success("🎉 Запись успешно удалена! Баланс пересчитан.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка удаления: {e}")
    else:
        st.write("Ручных операций для удаления пока нет.")
