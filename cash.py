# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 3.1 (категории + редактирование + фильтры + журнал изменений)

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


def get_user_name():
    user = st.session_state.get("user", {})
    return user.get("name") or user.get("role") or "Неизвестный"


def write_audit(action, table_name, record_id, old_data=None, new_data=None, comment=""):
    """Пишет запись в журнал изменений"""
    try:
        supabase.table("audit_log").insert({
            "user_name": get_user_name(),
            "action": action,
            "table_name": table_name,
            "record_id": str(record_id) if record_id is not None else None,
            "old_data": old_data,
            "new_data": new_data,
            "comment": comment
        }).execute()
    except Exception as e:
        st.warning(f"Не удалось записать в журнал: {e}")


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

        total_sum = filtered_ops["amount"].sum()
        count_ops = len(filtered_ops)
        needs_sum = filtered_ops[filtered_ops["category"] == "Нужды магазина"]["amount"].sum()
        supplier_sum = filtered_ops[filtered_ops["category"] == "Оплата контрагенту"]["amount"].sum()
        other_sum = filtered_ops[filtered_ops["category"] == "Без категории"]["amount"].sum()

        st.markdown("---")
        st.markdown("### 📊 Итоги по выбранному периоду и фильтру")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Всего операций", f"{count_ops}")
        c2.metric("Общая сумма", f"{total_sum:,.0f} сом")
        c3.metric("Нужды магазина", f"{needs_sum:,.0f} сом")
        c4.metric("Оплата контрагенту", f"{supplier_sum:,.0f} сом")

        if other_sum != 0:
            st.caption(f"Без категории: {other_sum:,.0f} сом")
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
        
        selected_op = next((op for op in ops_data if op["id"] == selected_id), None)
        
        if selected_op:
            current_cat = get_category_from_comment(selected_op.get("comment", ""))
            current_clean = clean_comment(selected_op.get("comment", ""))
            current_amount = float(selected_op.get("amount", 0))

            with st.form("edit_cash_form"):
                new_cat = st.selectbox(
                    "Тип расхода",
                    ["Нужды магазина", "Оплата контрагенту", "Без категории"],
                    index=["Нужды магазина", "Оплата контрагенту", "Без категории"].index(current_cat)
                    if current_cat in ["Нужды магазина", "Оплата контрагенту", "Без категории"] else 2
                )
                
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
                    if new_cat == "Нужды магазина":
                        final_comment = f"[НУЖДЫ] {new_comment}".strip()
                    elif new_cat == "Оплата контрагенту":
                        final_comment = f"[ПОСТАВЩИК] {new_comment}".strip()
                    else:
                        final_comment = new_comment

                    final_amount = -abs(new_amount_abs)

                    old_data = {
                        "date": selected_op.get("date"),
                        "amount": selected_op.get("amount"),
                        "comment": selected_op.get("comment")
                    }
                    new_data = {
                        "date": selected_op.get("date"),
                        "amount": final_amount,
                        "comment": final_comment
                    }

                    try:
                        supabase.table("cash_operations").update({
                            "amount": final_amount,
                            "comment": final_comment
                        }).eq("id", selected_id).execute()

                        write_audit(
                            action="UPDATE",
                            table_name="cash_operations",
                            record_id=selected_id,
                            old_data=old_data,
                            new_data=new_data,
                            comment="Редактирование кассовой операции"
                        )
                        st.success("Операция обновлена! Старые данные сохранены в журнале.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

                if delete_btn:
                    old_data = {
                        "date": selected_op.get("date"),
                        "amount": selected_op.get("amount"),
                        "comment": selected_op.get("comment")
                    }
                    try:
                        supabase.table("cash_operations").delete().eq("id", selected_id).execute()
                        write_audit(
                            action="DELETE",
                            table_name="cash_operations",
                            record_id=selected_id,
                            old_data=old_data,
                            new_data=None,
                            comment="Удаление кассовой операции"
                        )
                        st.success("Операция удалена! Данные сохранены в журнале.")
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
        comment = st.text_input(
            "Комментарий / Причина",
            placeholder="Например: Инкассация / Оплата за партию холодильников"
        )

        if st.form_submit_button("Списать из кассы", type="primary"):
            if op_type == "Нужды магазина":
                final_comment = f"[НУЖДЫ] {comment}".strip()
            else:
                final_comment = f"[ПОСТАВЩИК] {comment}".strip()

            new_row = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "amount": -amount,
                "comment": final_comment
            }

            try:
                res = supabase.table("cash_operations").insert(new_row).execute()
                new_id = res.data[0]["id"] if res.data else None

                write_audit(
                    action="CREATE",
                    table_name="cash_operations",
                    record_id=new_id,
                    old_data=None,
                    new_data=new_row,
                    comment="Создан расход из кассы"
                )
                st.success("✅ Расход зафиксирован и записан в журнал!")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

    # ==================== ЖУРНАЛ ИЗМЕНЕНИЙ ====================
    st.markdown("---")
    st.subheader("📋 Журнал изменений (касса)")

    try:
        audit_res = (
            supabase.table("audit_log")
            .select("*")
            .eq("table_name", "cash_operations")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        if not audit_res.data:
            st.info("Журнал пока пуст. После создания / изменения / удаления операций здесь появятся записи.")
        else:
            rows = []
            for a in audit_res.data:
                old_amount = None
                new_amount = None
                old_comment = None
                new_comment = None

                if a.get("old_data") and isinstance(a["old_data"], dict):
                    old_amount = a["old_data"].get("amount")
                    old_comment = a["old_data"].get("comment")
                if a.get("new_data") and isinstance(a["new_data"], dict):
                    new_amount = a["new_data"].get("amount")
                    new_comment = a["new_data"].get("comment")

                rows.append({
                    "Когда": str(a.get("created_at", ""))[:19],
                    "Кто": a.get("user_name", ""),
                    "Действие": a.get("action", ""),
                    "ID": a.get("record_id", ""),
                    "Было (сумма)": old_amount,
                    "Стало (сумма)": new_amount,
                    "Было (коммент)": old_comment,
                    "Стало (коммент)": new_comment,
                    "Примечание": a.get("comment", "")
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Не удалось загрузить журнал: {e}")
        st.info("Проверь, что таблица audit_log создана в Supabase.")
