# Магазин «Сулайман-Тоо» — Модуль: Состояние кассы магазина
# Версия программы: 1.7.6 (Полная защита от пустых значений дат NoneType)

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def format_date_display(date_str):
    if not date_str: return "-"
    return str(date_str)[:16]

def show_cash_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    
    if user_role == "Администратор":
        st.header("💵 Управление кассой и полный финансовый отчет")
    else:
        st.header("💵 Оперативная касса (Панель Кассира)")

    # 1. Загрузка данных из БД
    sales_res = supabase.table("sales").select("total_sale, payment, down_payment, day, profit").execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    payments_res = supabase.table("credit_payments").select("amount_paid, payment_date, client_id").execute()
    
    try: suppliers_res = supabase.table("supplier_payments").select("*").execute()
    except: suppliers_res = type('obj', (object,), {'data': []})

    clients_raw = supabase.table("clients").select("id, fio").execute()
    clients_dict = {c["id"]: c["fio"] for c in clients_raw.data} if clients_raw.data else {}

    # --- ТОЧНЫЙ ОСТАТОК НАЛИЧНЫХ «ЗДЕСЬ И СЕЙЧАС» ---
    all_cash_sales = sum(int(s["total_sale"] or 0) for s in sales_res.data if s.get("payment") == "Наличные")
    all_manual_and_downpayments = sum(float(op['amount'] or 0) for op in ops_res.data)
    all_collected_credits = sum(float(p.get("amount_paid", 0.0) or 0) for p in payments_res.data)
    all_supplier_flow = sum(float(sup['amount'] or 0) for sup in suppliers_res.data)

    net_cash_in_hand = all_cash_sales + all_manual_and_downpayments + all_collected_credits - all_supplier_flow

    # --- ПОКАЗАТЕЛИ СТРОГО ЗА СЕГОДНЯ ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_str_dot = datetime.now().strftime("%d.%m.%Y")

    # Безопасный расчет за сегодня (проверяем, что день s.get("day") существует)
    today_cash_sales = sum(
        int(s["total_sale"] or 0) 
        for s in sales_res.data 
        if s.get("payment") == "Наличные" and s.get("day") and str(s.get("day")) == today_str
    )
    
    today_ops = [
        op for op in ops_res.data 
        if op.get("date") and (str(op.get("date")).startswith(today_str) or str(op.get("date")).startswith(today_str_dot))
    ]
    
    today_down_payments = sum(float(op['amount'] or 0) for op in today_ops if "Перв. взнос" in str(op.get("comment", "")))
    today_manual_in = sum(float(op['amount'] or 0) for op in today_ops if float(op['amount'] or 0) > 0 and "Перв. взнос" not in str(op.get("comment", "")))
    today_expenses = sum(abs(float(op['amount'] or 0)) for op in today_ops if float(op['amount'] or 0) < 0)

    # ВЫВОД МЕТРИК
    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric("💰 Фактический остаток наличных в кассе", f"{int(net_cash_in_hand):,} сом")
    
    if user_role == "Администратор":
        all_profit = sum(float(s.get('profit', 0.0) or 0) for s in sales_res.data)
        c2.metric("📈 Общая чистая прибыль бизнеса", f"{int(all_profit):,} сом")
    else:
        c2.metric("🛍️ Дневная выручка от продаж", f"{int(today_cash_sales + today_down_payments):,} сом")

    # СВОДКА ЗА ДЕНЬ
    st.markdown("---")
    st.subheader("📋 Движение наличных за сегодняшний день")
    col_day1, col_day2, col_day3, col_day4 = st.columns(4)
    col_day1.metric("🟢 Прямые продажи (Нал)", f"{int(today_cash_sales):,} сом")
    col_day2.metric("📥 Перв. взносы (Рассрочка)", f"{int(today_down_payments):,} сом")
    col_day3.metric("➕ Прочие приходы/Сдача", f"{int(today_manual_in):,} сом")
    col_day4.metric("🔴 Выдачи / Расходы", f"{int(today_expenses):,} сом")

    # --- ПОСТРОЕНИЕ ТАБЛИЦЫ ВСЕХ ДОХОДОВ И РАСХОДОВ ---
    all_records = []

    # 1. Прямые наличные продажи
    for s in sales_res.data:
        if s.get("payment") == "Наличные":
            day_val = s.get("day") or today_str
            try: d_obj = datetime.strptime(day_val, "%Y-%m-%d").date()
            except: d_obj = datetime.now().date()
            
            all_records.append({
                "date_obj": d_obj,
                "Дата": day_val,
                "Тип операции": "🟢 ПРИХОД (Прямая продажа)",
                "Сумма (сом)": int(s["total_sale"] or 0),
                "Описание/Комментарий": "Продажа товара за наличный расчет"
            })

    # 2. Ручные кассовые операции
    for op in ops_res.data:
        amt = float(op['amount'] or 0)
        op_date = str(op.get('date') or today_str)
        try: d_obj = datetime.strptime(op_date[:10], "%Y-%m-%d").date()
        except:
            try: d_obj = datetime.strptime(op_date[:10], "%d.%m.%Y").date()
            except: d_obj = datetime.now().date()
            
        all_records.append({
            "date_obj": d_obj,
            "Дата": op_date,
            "Тип операции": "🟢 ПРИХОД (Касса)" if amt > 0 else "🔴 РАСХОД (Касса)",
            "Сумма (сом)": int(abs(amt)),
            "Описание/Комментарий": op.get('comment', '-')
        })

    # 3. Принятые платежи по рассрочке
    for p in payments_res.data:
        p_amt = float(p.get("amount_paid", 0.0) or 0)
        if p_amt > 0:
            p_date_str = p.get("payment_date") or today_str
            try: d_obj = datetime.strptime(p_date_str[:10], "%d.%m.%Y").date()
            except: d_obj = datetime.now().date()
            
            client_fio = clients_dict.get(p.get("client_id"), "Клиент")
            all_records.append({
                "date_obj": d_obj,
                "Дата": p_date_str,
                "Тип операции": "🟢 ПРИХОД (Взнос по рассрочке)",
                "Сумма (сом)": int(p_amt),
                "Описание/Комментарий": f"Оплата доли от {client_fio}"
            })

    # 4. Выплаты поставщикам
    for sup in suppliers_res.data:
        sup_date_str = sup.get("date") or today_str
        try: d_obj = datetime.strptime(sup_date_str[:10], "%d.%m.%Y").date()
        except: d_obj = datetime.now().date()
            
        all_records.append({
            "date_obj": d_obj,
            "Дата": sup_date_str,
            "Тип операции": "🔴 РАСХОД (Поставщику)",
            "Сумма (сом)": int(float(sup.get('amount', 0))),
            "Описание/Комментарий": f"Выплата контрагенту {sup.get('supplier', '-')}: {sup.get('comment', '')}"
        })

    # Вывод таблицы с фильтром периодов
    st.markdown("---")
    st.subheader("🔍 История и фильтрация кассового отчета")
    
    if all_records:
        df_all_cash = pd.DataFrame(all_records)
        
        if user_role == "Администратор":
            cash_range = st.date_input("Выберите период просмотра кассы", value=(df_all_cash['date_obj'].min(), df_all_cash['date_obj'].max()))
            if isinstance(cash_range, tuple) and len(cash_range) == 2:
                start_c, end_c = cash_range
                filtered_cash_df = df_all_cash[(df_all_cash['date_obj'] >= start_c) & (df_all_cash['date_obj'] <= end_c)]
            else:
                filtered_cash_df = pd.DataFrame()
        else:
            filtered_cash_df = df_all_cash[df_all_cash['date_obj'] == datetime.now().date()]
            st.info("Кассиру доступен просмотр кассового отчета только за текущий день.")

        if not filtered_cash_df.empty:
            filtered_cash_df = filtered_cash_df.sort_values(by="Дата", ascending=False)
            st.dataframe(filtered_cash_df.drop(columns=["date_obj"]), use_container_width=True, hide_index=True)
        else:
            st.write("За выбранный период кассовых движений не найдено.")
    else:
        st.write("История движений по кассе пуста.")

    # ФОРМА ИЗЪЯТИЯ (Только Администратор)
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
