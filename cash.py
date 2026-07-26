# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 3.0 (категории расходов + редактирование + фильтры)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database import supabase

def normalize_date(date_str):
    """Приводит любую дату к формату YYYY-MM-DD"""
    if not date_str:
        return None
    date_str = str(date_str).strip()[:10]
    
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except:
            continue
    return None


def get_category_from_comment(comment: str) -> str:
    """Определяет категорию по префиксу в комментарии"""
    comment = str(comment or "").strip()
    if comment.startswith("[НУЖДЫ]"):
        return "Нужды магазина"
    if comment.startswith("[ПОСТАВЩИК]"):
        return "Оплата контрагенту"
    return "Без категории"


def clean_comment(comment: str) -> str:
    """Убирает префикс категории из комментария"""
    comment = str(comment or "").strip()
    for prefix in ("[НУЖДЫ]", "[ПОСТАВЩИК]"):
        if comment.startswith(prefix):
            return comment[len(prefix):].strip()
    return comment


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

    # Считаем расходы по категориям
    needs_expense = 0.0
    supplier_expense = 0.0
    for op in ops_data:
        amount = float(op.get("amount", 0) or 0)
        if amount >= 0:
            continue
        cat = get_category_from_comment(op.get("comment", ""))
        if cat == "Нужды магазина":
            needs_expense += abs(amount)
        elif cat == "Оплата контрагенту":
            supplier_expense += abs(amount)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.0f} сом")
    c2.metric("📝 Долг клиентов", 
              f"{sum(float(s.get('credit_balance', 0) or 0) for s in sales_data if s.get('payment') == 'Рассрочка'):,.0f} сом")
    c3.metric("🏪 Расходы на нужды", f"{needs_expense:,.0f} сом")
    c4.metric("🚚 Выплаты поставщикам", f"{supplier_expense:,.0f} сом")

    st.markdown("---")
    st.subheader("📊 Остаток кассы по дням")

    # ==================== РАСЧЁТ ПО ДНЯМ ====================
    all_ops = []

    for s in sales_data:
        if s.get("payment") == "Наличные":
            day = normalize_date(s.get("day"))
            if day:
                all_ops.append({
                    "day": day,
                    "cash_sales": float(s.get("total_sale", 0)),
                    "inflow": 0.0,
                    "outflow": 0.0
                })

    for op in ops_data:
        day = normalize_date(op.get("date"))
        if not day:
            continue
        amount = float(op.get("amount", 0))
        all_ops.append({
            "day": day,
            "cash_sales": 0.0,
            "inflow": amount if amount > 0 else 0.0,
            "outflow": -amount if amount < 0 else 0.0
        })

    if all_ops:
        df_all = pd.DataFrame(all_ops)
        
        daily = df_all.groupby('day').agg({
            'cash_sales': 'sum',
            'inflow': 'sum',
            'outflow': 'sum'
        }).reset_index()

        daily['day_dt'] = pd.to_datetime(daily['day'])
        daily = daily.sort_values('day_dt')

        daily['net'] = daily['cash_sales'] + daily['inflow'] - daily['outflow']
        daily['balance_end'] = daily['net'].cumsum()
        daily['balance_start'] = daily['balance_end'].shift(1).fillna(0)

        display = daily[['day', 'balance_start', 'cash_sales', 'inflow', 'outflow', 'balance_end']].copy()
        display.columns = [
            'Дата',
            'Остаток на начало дня',
            'Продажи наличкой',
            'Приходы (взносы, платежи)',
            'Расходы / Изъятия',
            'Остаток на конец дня'
        ]

        for col in display.columns[1:]:
            display[col] = display[col].map('{:,.0f}'.format)

        st.dataframe(display, use_container_width=True, hide_index=True)

        last_end = daily['balance_end'].iloc[-1]
        st.caption(f"Последний остаток в таблице: **{last_end:,.0f} сом** | Текущий остаток кассы: **{current_cash_in_hand:,.0f} сом**")
    else:
        st.info("Пока нет операций для расчёта.")

    # ==================== ИСТОРИЯ ОПЕРАЦИЙ ====================
    st.markdown("---")
    st.subheader("📜 История кассовых операций")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        start_date = st.date_input("Начало периода", value=datetime.now().date() - timedelta(days=30))
    with col_f2:
        end_date = st.date_input("Конец периода", value=datetime.now().date())
    with col_f3:
        filter_cat = st.selectbox("Фильтр по типу", ["Все", "Нужды магазина", "Оплата контрагенту", "Без категории"])

    df_ops = pd.DataFrame(ops_data) if ops_data else pd.DataFrame()
    if not df_ops.empty:
        try:
            df_ops['date_norm'] = df_ops['date'].apply(normalize_date)
            df_ops['date_obj'] = pd.to_datetime(df_ops['date_norm'], errors='coerce').dt.date
            df_ops['category'] = df_ops['comment'].apply(get_category_from_comment)
            filtered_ops = df_ops[(df_ops['date_obj'] >= start_date) & (df_ops['date_obj'] <= end_date)].copy()
            
            if filter_cat != "Все":
                filtered_ops = filtered_ops[filtered_ops['category'] == filter_cat]
        except:
            filtered_ops = df_ops
    else:
        filtered_ops = pd.DataFrame()

    if not filtered_ops.empty:
        display_df = filtered_ops[["id", "date", "amount", "category", "comment"]].copy()
        display_df["amount"] = display_df["amount"].map('{:,.0f}'.format)
        display_df = display_df.rename(columns={
            "id": "ID",
            "date": "Дата",
            "amount": "Сумма",
            "category": "Тип",
            "comment": "Комментарий"
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Операций за выбранный период нет.")

    # ==================== РЕДАКТИРОВАНИЕ / УДАЛЕНИЕ ====================
    if user_role == "Администратор" and not filtered_ops.empty:
        st.markdown("---")
        st.subheader("✏️ Редактировать / Удалить операцию")

        options = {
            f"{row['id']} | {row['date']} | {int(row['amount']):,} сом | {get_category_from_comment(row.get('comment',''))} | {clean_comment(row.get('comment',''))}": row['id']
            for _, row in filtered_ops.iterrows()
        }
        selected_label = st.selectbox("Выберите операцию", list(options.keys()), key="edit_op_select")
        selected_id = options[selected_label]
        
        # Находим полные данные
        selected_op = next((op for op in ops_data if op["id"] == selected_id), None)
        
        if selected_op:
            current_cat = get_category_from_comment(selected_op.get("comment", ""))
            current_clean = clean_comment(selected_op.get("comment", ""))
            current_amount = float(selected_op.get("amount", 0))

            with st.form("edit_cash_form"):
                new_cat = st.selectbox(
                    "Тип расхода",
                    ["Нужды магазина", "Оплата контрагенту", "Без категории"],
                    index=["Нужды магазина", "Оплата контрагенту", "Без категории"].index(current_cat) if current_cat in ["Нужды магазина", "Оплата контрагенту", "Без категории"] else 2
                )
                
                # Сумма всегда показываем как положительную для удобства
                new_amount_abs = st.number_input(
                    "Сумма (сом)", 
                    min_value=0.0, 
                    value=abs(current_amount),
                    step=100.0
                )
                
                new_comment = st.text_input("Комментарий (без префикса)", value=current_clean)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    save_btn = st.form_submit_button("💾 Сохранить изменения", type="primary")
                with col_btn2:
                    delete_btn = st.form_submit_button("🗑️ Удалить операцию")

                if save_btn:
                    # Формируем новый комментарий с префиксом
                    if new_cat == "Нужды магазина":
                        final_comment = f"[НУЖДЫ] {new_comment}".strip()
                    elif new_cat == "Оплата контрагенту":
                        final_comment = f"[ПОСТАВЩИК] {new_comment}".strip()
                    else:
                        final_comment = new_comment

                    # Сохраняем сумму как отрицательную (это расход)
                    final_amount = -abs(new_amount_abs)

                    try:
                        supabase.table("cash_operations").update({
                            "amount": final_amount,
                            "comment": final_comment
                        }).eq("id", selected_id).execute()
                        st.success("Операция обновлена!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

                if delete_btn:
                    try:
                        supabase.table("cash_operations").delete().eq("id", selected_id).execute()
                        st.success("Операция удалена!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка удаления: {e}")

    # ==================== НОВАЯ ОПЕРАЦИЯ ====================
    st.markdown("---")
    st.subheader("📤 Новый расход из кассы")

    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип расхода", [
            "Нужды магазина",
            "Оплата контрагенту"
        ])
        
        amount = st.number_input("Сумма, сом", min_value=1.0, value=1000.0, step=100.0)
        comment = st.text_input("Комментарий / Причина", 
                                placeholder="Например: Инкассация / Оплата за партию холодильников")

        if st.form_submit_button("Списать из кассы", type="primary"):
            if op_type == "Нужды магазина":
                final_comment = f"[НУЖДЫ] {comment}".strip()
            else:
                final_comment = f"[ПОСТАВЩИК] {comment}".strip()

            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "amount": -amount,
                "comment": final_comment
            }).execute()
            st.success("✅ Расход зафиксирован!")
            st.rerun()
