# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 3.2 (сверка дня: утро, продажи, погашения, расходы, вечер)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database import supabase

def normalize_date(date_str):
    if not date_str:
        return None
    date_str = str(date_str).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def get_category_from_comment(comment: str) -> str:
    comment = str(comment or "").strip()
    if comment.startswith("[НУЖДЫ]"):
        return "Нужды магазина"
    if comment.startswith("[ПОСТАВЩИК]"):
        return "Оплата контрагенту"
    return "Без категории"


def clean_comment(comment: str) -> str:
    comment = str(comment or "").strip()
    for prefix in ("[НУЖДЫ]", "[ПОСТАВЩИК]"):
        if comment.startswith(prefix):
            return comment[len(prefix):].strip()
    return comment


def get_user_name():
    user = st.session_state.get("user", {})
    return user.get("name") or user.get("role") or "Неизвестный"


def write_audit(action, table_name, record_id, old_data=None, new_data=None, comment=""):
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


def build_day_rows(sales_data, ops_data):
    rows = []
    for s in sales_data:
        if s.get("payment") != "Наличные":
            continue
        day = normalize_date(s.get("day")) or normalize_date(s.get("date"))
        if not day:
            continue
        rows.append({
            "day": day,
            "sales": float(s.get("total_sale", 0) or 0),
            "inflow": 0.0,
            "needs": 0.0,
            "supplier": 0.0,
            "other_out": 0.0,
        })
    for op in ops_data:
        day = normalize_date(op.get("date"))
        if not day:
            continue
        amount = float(op.get("amount", 0) or 0)
        cat = get_category_from_comment(op.get("comment", ""))
        row = {"day": day, "sales": 0.0, "inflow": 0.0, "needs": 0.0, "supplier": 0.0, "other_out": 0.0}
        if amount > 0:
            row["inflow"] = amount
        elif cat == "Нужды магазина":
            row["needs"] = abs(amount)
        elif cat == "Оплата контрагенту":
            row["supplier"] = abs(amount)
        else:
            row["other_out"] = abs(amount)
        rows.append(row)
    return rows


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

    full_cash_sales = sum(float(s.get("total_sale", 0) or 0) for s in sales_data if s.get("payment") == "Наличные")
    manual_cash_flow = sum(float(op.get("amount", 0) or 0) for op in ops_data)
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
    c2.metric("📝 Долг клиентов", f"{sum(float(s.get('credit_balance', 0) or 0) for s in sales_data if s.get('payment') == 'Рассрочка'):,.0f} сом")
    c3.metric("🏪 Расходы на нужды", f"{needs_expense:,.0f} сом")
    c4.metric("🚚 Выплаты поставщикам", f"{supplier_expense:,.0f} сом")

    st.markdown("---")
    st.subheader("📅 Сверка кассы за день")

    day_rows = build_day_rows(sales_data, ops_data)
    if not day_rows:
        st.info("Пока нет операций для сверки.")
    else:
        daily = pd.DataFrame(day_rows).groupby("day", as_index=False).sum()
        daily["day_dt"] = pd.to_datetime(daily["day"])
        daily = daily.sort_values("day_dt")
        daily["net"] = daily["sales"] + daily["inflow"] - daily["needs"] - daily["supplier"] - daily["other_out"]
        daily["balance_end"] = daily["net"].cumsum()
        daily["balance_start"] = daily["balance_end"].shift(1).fillna(0)

        check_day = st.date_input("Какой день сверить", value=datetime.now().date(), key="cash_check_day")
        day_key = check_day.strftime("%Y-%m-%d")
        before = daily[daily["day_dt"] < pd.Timestamp(check_day)]
        opening = float(before["balance_end"].iloc[-1]) if not before.empty else 0.0
        today_row = daily[daily["day"] == day_key]
        if today_row.empty:
            sales_sum = inflow = needs = supplier = other_out = 0.0
        else:
            sales_sum = float(today_row["sales"].iloc[0])
            inflow = float(today_row["inflow"].iloc[0])
            needs = float(today_row["needs"].iloc[0])
            supplier = float(today_row["supplier"].iloc[0])
            other_out = float(today_row["other_out"].iloc[0])
        closing = opening + sales_sum + inflow - needs - supplier - other_out

        m1, m2, m3 = st.columns(3)
        m1.metric("Остаток на утро", f"{opening:,.0f} сом")
        m2.metric("Остаток на вечер", f"{closing:,.0f} сом")
        m3.metric("Изменение за день", f"{closing - opening:,.0f} сом")

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Продажи наличкой", f"{sales_sum:,.0f}")
        d2.metric("Погашения и взносы", f"{inflow:,.0f}")
        d3.metric("Нужды магазина", f"{needs:,.0f}")
        d4.metric("Оплата поставщикам", f"{supplier:,.0f}")
        if other_out:
            st.caption(f"Прочие изъятия за день: {other_out:,.0f} сом")

        if check_day == datetime.now().date():
            if abs(closing - current_cash_in_hand) < 1:
                st.success(f"Вечер совпадает с кассой сейчас: {current_cash_in_hand:,.0f} сом")
            else:
                st.warning(f"Вечер {closing:,.0f}, а в кассе сейчас {current_cash_in_hand:,.0f}. Разница {current_cash_in_hand - closing:,.0f}.")

        st.markdown("**Движения за выбранный день**")
        moves = []
        for s in sales_data:
            if s.get("payment") != "Наличные":
                continue
            if (normalize_date(s.get("day")) or normalize_date(s.get("date"))) != day_key:
                continue
            moves.append({
                "Время": str(s.get("date", ""))[:16],
                "Тип": "Продажа наличкой",
                "Сумма": int(float(s.get("total_sale", 0) or 0)),
                "Комментарий": str(s.get("name", ""))[:70],
            })
        for op in ops_data:
            if normalize_date(op.get("date")) != day_key:
                continue
            amount = float(op.get("amount", 0) or 0)
            cat = get_category_from_comment(op.get("comment", ""))
            if amount > 0:
                kind = "Погашение / взнос"
            elif cat == "Нужды магазина":
                kind = "Нужды"
            elif cat == "Оплата контрагенту":
                kind = "Поставщик"
            else:
                kind = "Прочее"
            moves.append({
                "Время": str(op.get("date", ""))[:16],
                "Тип": kind,
                "Сумма": int(amount),
                "Комментарий": clean_comment(op.get("comment", ""))[:70],
            })
        if moves:
            st.dataframe(pd.DataFrame(moves), use_container_width=True, hide_index=True)
        else:
            st.info("За этот день движений нет. Остаток на вечер равен утру.")

        st.markdown("#### Все дни")
        show = daily.sort_values("day_dt", ascending=False)[[
            "day", "balance_start", "sales", "inflow", "needs", "supplier", "other_out", "balance_end"
        ]].copy()
        show.columns = [
            "Дата", "На утро", "Продажи", "Погашения и взносы", "Нужды", "Поставщики", "Прочие", "На вечер"
        ]
        for col in show.columns[1:]:
            show[col] = show[col].map("{:,.0f}".format)
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption(f"Последний вечер: **{daily['balance_end'].iloc[-1]:,.0f} сом** | Касса сейчас: **{current_cash_in_hand:,.0f} сом**")

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
            df_ops["date_norm"] = df_ops["date"].apply(normalize_date)
            df_ops["date_obj"] = pd.to_datetime(df_ops["date_norm"], errors="coerce").dt.date
            df_ops["category"] = df_ops["comment"].apply(get_category_from_comment)
            filtered_ops = df_ops[(df_ops["date_obj"] >= start_date) & (df_ops["date_obj"] <= end_date)].copy()
            if filter_cat != "Все":
                filtered_ops = filtered_ops[filtered_ops["category"] == filter_cat]
        except Exception:
            filtered_ops = df_ops
    else:
        filtered_ops = pd.DataFrame()

    if not filtered_ops.empty:
        display_df = filtered_ops[["id", "date", "amount", "category", "comment"]].copy()
        display_df["amount"] = display_df["amount"].map("{:,.0f}".format)
        display_df = display_df.rename(columns={
            "id": "ID", "date": "Дата", "amount": "Сумма", "category": "Тип", "comment": "Комментарий"
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        total_sum = filtered_ops["amount"].sum()
        st.caption(f"Операций: {len(filtered_ops)} | Сумма: {total_sum:,.0f} сом")
    else:
        st.info("Операций за выбранный период нет.")

    if user_role == "Администратор" and not filtered_ops.empty:
        st.markdown("---")
        st.subheader("✏️ Редактировать / Удалить операцию")
        options = {
            f"{row['id']} | {row['date']} | {int(row['amount']):,} сом | {get_category_from_comment(row.get('comment',''))} | {clean_comment(row.get('comment',''))}": row["id"]
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
                cats = ["Нужды магазина", "Оплата контрагенту", "Без категории"]
                new_cat = st.selectbox("Тип расхода", cats, index=cats.index(current_cat) if current_cat in cats else 2)
                new_amount_abs = st.number_input("Сумма (сом)", min_value=0.0, value=abs(current_amount), step=100.0)
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
                    old_data = {"date": selected_op.get("date"), "amount": selected_op.get("amount"), "comment": selected_op.get("comment")}
                    new_data = {"date": selected_op.get("date"), "amount": final_amount, "comment": final_comment}
                    try:
                        supabase.table("cash_operations").update({"amount": final_amount, "comment": final_comment}).eq("id", selected_id).execute()
                        write_audit("UPDATE", "cash_operations", selected_id, old_data, new_data, "Редактирование кассовой операции")
                        st.success("Операция обновлена.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
                if delete_btn:
                    old_data = {"date": selected_op.get("date"), "amount": selected_op.get("amount"), "comment": selected_op.get("comment")}
                    try:
                        supabase.table("cash_operations").delete().eq("id", selected_id).execute()
                        write_audit("DELETE", "cash_operations", selected_id, old_data, None, "Удаление кассовой операции")
                        st.success("Операция удалена.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка удаления: {e}")

    st.markdown("---")
    st.subheader("📤 Новый расход из кассы")
    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип расхода", ["Нужды магазина", "Оплата контрагенту"])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=1000.0, step=100.0)
        comment = st.text_input("Комментарий / Причина", placeholder="Например: оплата за партию холодильников")
        if st.form_submit_button("Списать из кассы", type="primary"):
            final_comment = f"[НУЖДЫ] {comment}".strip() if op_type == "Нужды магазина" else f"[ПОСТАВЩИК] {comment}".strip()
            new_row = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "amount": -amount, "comment": final_comment}
            try:
                res = supabase.table("cash_operations").insert(new_row).execute()
                new_id = res.data[0]["id"] if res.data else None
                write_audit("CREATE", "cash_operations", new_id, None, new_row, "Создан расход из кассы")
                st.success("Расход зафиксирован.")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

    st.markdown("---")
    st.subheader("📋 Журнал изменений (касса)")
    try:
        audit_res = (
            supabase.table("audit_log").select("*").eq("table_name", "cash_operations")
            .order("created_at", desc=True).limit(100).execute()
        )
        if not audit_res.data:
            st.info("Журнал пока пуст.")
        else:
            rows = []
            for a in audit_res.data:
                old_amount = a.get("old_data", {}).get("amount") if isinstance(a.get("old_data"), dict) else None
                new_amount = a.get("new_data", {}).get("amount") if isinstance(a.get("new_data"), dict) else None
                rows.append({
                    "Когда": str(a.get("created_at", ""))[:19],
                    "Кто": a.get("user_name", ""),
                    "Действие": a.get("action", ""),
                    "ID": a.get("record_id", ""),
                    "Было": old_amount,
                    "Стало": new_amount,
                    "Примечание": a.get("comment", ""),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Не удалось загрузить журнал: {e}")
