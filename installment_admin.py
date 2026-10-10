# Магазин «Сулайман-Тоо» — Модуль: Правка рассрочек (только Администратор)
# Версия: 1.0
# - правка дат и сумм неоплаченных платежей, добавление/удаление неоплаченных строк;
# - правка суммы рассрочки по договору (credit_balance) со сверкой графика;
# - аннулирование принятой оплаты: обратная (минусовая) запись в кассу, строка снова неоплачена.
# Каждое изменение пишется в журнал audit_log (кто, когда, причина, было/стало).
# Права проверяются при открытии страницы И перед каждой записью в базу (по таблице users).

from datetime import datetime

import pandas as pd
import streamlit as st

from database import supabase
from installment_logic import (
    STATUS_UNPAID, generate_open_rows, is_locked, num, parse_day, plan_annulment,
    plan_schedule_save, reuse_ids, row_expected, row_paid, schedule_totals, sort_rows,
)

ADMIN_ROLE = "Администратор"
MENU_ITEM = "🛠️ Правка рассрочек"
MIGRATION_FILE = "migrations/001_audit_log.sql"


class NotAdmin(Exception):
    pass


def current_admin():
    """Возвращает пользователя-админа, перепроверив роль в таблице users, иначе None."""
    user = st.session_state.get("user") or {}
    if user.get("role") != ADMIN_ROLE or not user.get("id"):
        return None
    try:
        rows = supabase.table("users").select("id, username, role").eq("id", user["id"]).execute().data or []
    except Exception:
        return None
    if rows and rows[0].get("role") == ADMIN_ROLE:
        return rows[0]
    return None


def require_admin():
    admin = current_admin()
    if not admin:
        raise NotAdmin("Действие доступно только администратору")
    return admin


def admin_name(admin):
    return f"{admin.get('username') or 'admin'} (id {admin.get('id')}, {ADMIN_ROLE})"


def audit_available():
    try:
        supabase.table("audit_log").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def write_audit(admin, action, table_name, record_id, old_data, new_data, comment):
    supabase.table("audit_log").insert({
        "user_name": admin_name(admin),
        "action": action,
        "table_name": table_name,
        "record_id": str(record_id) if record_id is not None else None,
        "old_data": old_data,
        "new_data": new_data,
        "comment": comment,
    }).execute()


# ---------- запись в базу ----------

def apply_schedule_plan(sale, plan, reason):
    """Выполняет план правки графика. Перед записью ещё раз проверяет админа."""
    admin = require_admin()
    if plan["errors"]:
        raise ValueError("; ".join(plan["errors"]))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note = f"Правка графика договора {sale.get('id')}: {reason}"
    for u in plan["updates"]:
        supabase.table("credit_payments").update(u["new"]).eq("id", u["id"]).execute()
        write_audit(admin, "SCHEDULE_UPDATE", "credit_payments", u["id"], u["old"], {**u["new"], "at": stamp}, note)
    for row in plan["inserts"]:
        res = supabase.table("credit_payments").insert(row).execute()
        new_id = res.data[0].get("id") if getattr(res, "data", None) else None
        write_audit(admin, "SCHEDULE_INSERT", "credit_payments", new_id, None, {**row, "at": stamp}, note)
    for row in plan["deletes"]:
        if is_locked(row):  # страховка: оплаченные строки не удаляем никогда
            continue
        supabase.table("credit_payments").delete().eq("id", row["id"]).execute()
        old = {k: row.get(k) for k in ("sale_id", "due_date", "amount_expected", "amount_paid", "status")}
        write_audit(admin, "SCHEDULE_DELETE", "credit_payments", row["id"], old, {"at": stamp}, note)
    if plan["contract_update"]:
        cu = plan["contract_update"]
        supabase.table("sales").update(cu["new"]).eq("id", sale["id"]).execute()
        write_audit(admin, "CONTRACT_UPDATE", "sales", sale["id"], cu["old"], {**cu["new"], "at": stamp}, note)


def apply_annulment(plan, sale_id):
    """
    1) строка графика: amount_paid уменьшается (с проверкой, что её никто не поменял);
    2) в кассу — минусовая запись на ту же сумму (история не удаляется);
    3) журнал. Если касса не записалась — строку возвращаем как было.
    """
    admin = require_admin()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    res = (
        supabase.table("credit_payments").update(plan["new"])
        .eq("id", plan["row_id"]).eq("amount_paid", plan["old"]["amount_paid"]).execute()
    )
    if not getattr(res, "data", None):
        raise RuntimeError("Платёж уже изменился (возможно, его только что приняли или аннулировали). Обновите страницу.")
    try:
        cash = supabase.table("cash_operations").insert(plan["cash_entry"]).execute()
    except Exception as e:
        supabase.table("credit_payments").update(plan["old"]).eq("id", plan["row_id"]).execute()
        raise RuntimeError(f"Не удалось записать возврат в кассу, платёж оставлен как был: {e}")
    cash_id = cash.data[0].get("id") if getattr(cash, "data", None) else None
    note = f"Аннулирование оплаты {plan['amount']} сом по договору {sale_id}: {plan['reason']}"
    write_audit(admin, "PAYMENT_ANNUL", "credit_payments", plan["row_id"], plan["old"],
                {**plan["new"], "cash_operation_id": cash_id, "at": stamp}, note)
    write_audit(admin, "CREATE", "cash_operations", cash_id, None, plan["cash_entry"], note)
    return cash_id


# ---------- экран ----------

def money(v):
    return f"{num(v):,.0f}".replace(",", " ") + " сом"


def due_txt(row):
    d = parse_day(row.get("due_date"))
    return d.strftime("%d.%m.%Y") if d else str(row.get("due_date") or "—")


def draft_from_rows(rows):
    return [{"id": str(r.get("id")), "due": parse_day(r.get("due_date")), "amount": row_expected(r)}
            for r in sort_rows(rows) if not is_locked(r)]


def draft_key(sale_id):
    return f"inst_draft_{sale_id}"


def reset_draft(sale_id, rows):
    st.session_state[draft_key(sale_id)] = draft_from_rows(rows)
    st.session_state[f"inst_ver_{sale_id}"] = st.session_state.get(f"inst_ver_{sale_id}", 0) + 1


def show_installment_admin_page():
    st.title(MENU_ITEM)
    admin = current_admin()
    if not admin:
        st.error("⛔ Этот раздел только для администратора. Войдите как Администратор в меню слева.")
        return

    st.caption("Оплаченные платежи заблокированы. Чтобы исправить принятую оплату — сначала аннулируйте её "
               "(деньги вычтутся из кассы), исправьте график, затем примите оплату заново в «👥 Клиенты → 💳 Рассрочки».")

    flash_slot = st.empty()  # всегда на одном месте, чтобы раскрытые блоки ниже не сворачивались
    flash = st.session_state.pop("inst_flash", None)
    if flash:
        flash_slot.success(flash)

    can_write = audit_available()
    if not can_write:
        st.error(
            "Журнал изменений (таблица audit_log) недоступен, поэтому правки отключены. "
            f"Выполните файл `{MIGRATION_FILE}` в Supabase → SQL Editor и обновите страницу."
        )

    try:
        clients = supabase.table("clients").select("*").order("fio").execute().data or []
        sales = supabase.table("sales").select("*").eq("payment", "Рассрочка").execute().data or []
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return
    clients_map = {c["id"]: c for c in clients}
    with_sales = [c for c in clients if any(s.get("client_id") == c["id"] for s in sales)]
    if not with_sales:
        st.info("Договоров рассрочки нет.")
        return

    search = st.text_input("Поиск клиента по фамилии или телефону", key="inst_search")
    found = with_sales
    if search:
        q = search.strip().lower()
        found = [c for c in with_sales if q in str(c.get("fio") or "").lower() or q in str(c.get("phone") or "")]
    if not found:
        st.warning("Клиент не найден.")
        return
    c_opts = {f"{c.get('fio') or 'Без имени'} ({c.get('phone') or 'без телефона'})": c["id"] for c in found}
    cid = c_opts[st.selectbox("Клиент", list(c_opts.keys()), key="inst_client")]
    client = clients_map[cid]

    client_sales = sorted([s for s in sales if s.get("client_id") == cid], key=lambda s: str(s.get("date") or ""))
    s_opts = {f"{str(s.get('name') or s.get('id'))[:70]} | {money(s.get('credit_balance'))}": s for s in client_sales}
    sale = s_opts[st.selectbox("Договор", list(s_opts.keys()), key="inst_sale")]
    sid = sale["id"]

    try:
        rows = supabase.table("credit_payments").select("*").eq("sale_id", sid).execute().data or []
    except Exception as e:
        st.error(f"Ошибка загрузки графика: {e}")
        return
    rows = sort_rows(rows)
    totals = schedule_totals(sale.get("credit_balance"), rows)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Сумма рассрочки", money(totals["credit_balance"]))
    m2.metric("Взнос", money(sale.get("down_payment")))
    m3.metric("Оплачено по графику", money(totals["paid"]))
    m4.metric("Остаток долга", money(totals["remaining"]))

    # ----- оплаченные строки: только просмотр и аннулирование -----
    locked = [r for r in rows if is_locked(r)]
    st.subheader("🔒 Оплаченные платежи")
    if not locked:
        st.info("Оплат по этому договору пока нет.")
    else:
        st.dataframe(pd.DataFrame([{
            "Дата": due_txt(r), "Ожидается": int(row_expected(r)), "Оплачено": int(row_paid(r)),
            "Статус": r.get("status") or "", "ID": str(r.get("id")),
        } for r in locked]), use_container_width=True, hide_index=True)

        with st.expander("↩️ Аннулировать платёж"):
            l_opts = {f"{due_txt(r)} | оплачено {money(row_paid(r))} | #{r.get('id')}": r for r in locked}
            row = l_opts[st.selectbox("Какой платёж", list(l_opts.keys()), key=f"annul_row_{sid}")]
            paid = row_paid(row)
            amount = st.number_input("Сумма аннулирования, сом", min_value=0.0, max_value=float(paid),
                                     value=float(paid), step=100.0, key=f"annul_amt_{row.get('id')}")
            reason = st.text_area("Причина (обязательно)", key=f"annul_reason_{row.get('id')}")
            confirm = st.checkbox(f"Подтверждаю: из кассы будет вычтено {money(amount)}, платёж станет неоплаченным",
                                  key=f"annul_ok_{row.get('id')}")
            if st.button("↩️ Аннулировать платёж", type="primary", disabled=not can_write, key=f"annul_btn_{sid}"):
                if not confirm:
                    st.error("Поставьте галочку подтверждения.")
                else:
                    try:
                        plan = plan_annulment(row, amount, reason, client.get("fio") or "клиент")
                        apply_annulment(plan, sid)
                        st.session_state.pop(draft_key(sid), None)
                        st.session_state["inst_flash"] = (
                            f"Аннулировано {money(plan['amount'])}. Касса уменьшена на эту сумму. "
                            "Исправьте график и примите оплату заново в «👥 Клиенты»."
                        )
                        st.rerun()
                    except NotAdmin as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(str(e))

    # ----- неоплаченные строки: правка -----
    st.subheader("✏️ Неоплаченные платежи")
    if draft_key(sid) not in st.session_state:
        reset_draft(sid, rows)
    draft = st.session_state[draft_key(sid)]
    ver = st.session_state.get(f"inst_ver_{sid}", 0)

    new_balance = st.number_input(
        "Сумма рассрочки по договору (долг с наценкой), сом", min_value=0.0,
        value=float(num(sale.get("credit_balance"))), step=100.0, key=f"inst_balance_{sid}",
    )
    locked_expected = sum(row_expected(r) for r in locked)
    open_needed = new_balance - locked_expected

    with st.expander("⚡ Быстро разложить остаток по месяцам"):
        st.caption(f"Нужно распределить: {money(open_needed)} (сумма рассрочки минус оплаченные строки).")
        last_due = max([parse_day(r.get("due_date")) for r in locked if parse_day(r.get("due_date"))], default=None)
        first_default = parse_day(draft[0]["due"]) if draft else None
        first_default = first_default or (last_due and last_due.replace(day=min(last_due.day, 28))) or datetime.now().date()
        monthly = st.number_input("Ежемесячный платёж, сом", min_value=0.0,
                                  value=float(int(draft[0]["amount"])) if draft else 1000.0, step=100.0, key=f"inst_monthly_{sid}")
        first_due = st.date_input("Дата первого неоплаченного платежа", value=first_default, key=f"inst_first_{sid}")
        if st.button("Заполнить таблицу ниже", key=f"inst_fill_{sid}"):
            try:
                st.session_state[draft_key(sid)] = reuse_ids(generate_open_rows(open_needed, monthly, first_due), draft)
                st.session_state[f"inst_ver_{sid}"] = ver + 1
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    df = pd.DataFrame(draft, columns=["id", "due", "amount"])
    df["id"] = df["id"].astype("object")
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"inst_editor_{sid}_{ver}",
        column_config={
            "id": st.column_config.TextColumn("ID", disabled=True, help="Пусто — новая строка"),
            "due": st.column_config.DateColumn("Дата платежа", format="DD.MM.YYYY", required=True),
            "amount": st.column_config.NumberColumn("Сумма, сом", min_value=0.0, step=100.0, required=True),
        },
    )
    new_draft = [{"id": r.get("id"), "due": r.get("due"), "amount": r.get("amount")}
                 for r in edited.to_dict("records")
                 if not (pd.isna(r.get("due")) and pd.isna(r.get("amount")))]
    st.button("↺ Отменить правки в таблице", key=f"inst_reset_{sid}", on_click=reset_draft, args=(sid, rows))

    plan = plan_schedule_save(sale, rows, new_draft, new_balance)
    chk = plan["check"]
    st.markdown(
        f"**Сверка:** график {money(chk['schedule_total'])} · сумма рассрочки {money(chk['credit_balance'])} · "
        f"разница {money(chk['diff'])}"
    )
    force = False
    if plan["errors"]:
        for err in plan["errors"]:
            st.error(err)
    elif not chk["ok"]:
        st.warning("Сумма графика не совпадает с суммой рассрочки по договору. Остаток долга клиента считается "
                   "от суммы рассрочки, поэтому лучше выровнять. Можно сохранить и так, если это осознанно.")
        force = st.checkbox("Всё равно сохранить с разницей", key=f"inst_force_{sid}")
    if plan["changed"]:
        st.caption(f"Будет изменено: {len(plan['updates'])}, добавлено: {len(plan['inserts'])}, "
                   f"удалено: {len(plan['deletes'])}" + (", сумма рассрочки по договору" if plan["contract_update"] else ""))
    reason = st.text_input("Причина правки (для журнала, обязательно)", key=f"inst_reason_{sid}")

    ready = can_write and plan["changed"] and not plan["errors"] and (chk["ok"] or force)
    if st.button("💾 Сохранить график", type="primary", disabled=not ready, key=f"inst_save_{sid}"):
        if len(reason.strip()) < 3:
            st.error("Укажите причину правки.")
        else:
            try:
                apply_schedule_plan(sale, plan, reason.strip())
                st.session_state.pop(draft_key(sid), None)
                st.session_state["inst_flash"] = "График сохранён."
                st.rerun()
            except NotAdmin as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Ошибка сохранения: {e}. Обновите страницу и проверьте график.")

    with st.expander("📋 Журнал правок этого договора"):
        show_contract_audit(sid, rows)


def show_contract_audit(sale_id, rows):
    ids = {str(r.get("id")) for r in rows}
    try:
        log = (supabase.table("audit_log").select("*").in_("table_name", ["credit_payments", "sales"])
               .order("created_at", desc=True).limit(300).execute().data or [])
    except Exception as e:
        st.info(f"Журнал недоступен: {e}")
        return
    mine = [a for a in log if str(a.get("record_id")) in ids or str(a.get("record_id")) == str(sale_id)
            or str(sale_id) in str(a.get("comment") or "")]
    if not mine:
        st.info("Правок пока не было.")
        return
    st.dataframe(pd.DataFrame([{
        "Когда": str(a.get("created_at") or (a.get("new_data") or {}).get("at") or "")[:19],
        "Кто": a.get("user_name", ""),
        "Действие": a.get("action", ""),
        "ID": a.get("record_id", ""),
        "Было": str(a.get("old_data") or ""),
        "Стало": str(a.get("new_data") or ""),
        "Причина": a.get("comment", ""),
    } for a in mine]), use_container_width=True, hide_index=True)
