# Магазин «Сулайман-Тоо» — Модуль: Долг с поставщиком (Икром). Только суммы, без фото.
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from database import supabase, create_new_user
from supplier_logic import (
    SUPPLIER_ROLE, TYPES, TYPE_GOODS, TYPE_PAYMENT, TYPE_RETURN,
    side_of_role, allowed_types, can_accept, can_delete_entry, balance, pending_balance, validate_amount,
)
from stock_logic import is_admin

TYPE_LABELS = {TYPE_GOODS: "📦 Товар пришёл", TYPE_PAYMENT: "💸 Оплата", TYPE_RETURN: "↩️ Возврат"}

MIGRATION_HINT = (
    "Таблица учёта долга ещё не создана. Администратору нужно один раз выполнить файл "
    "`migrations/005_supplier_debt.sql` в Supabase → SQL Editor → Run."
)


def load_entries():
    try:
        return supabase.table("supplier_ledger").select("*").order("created_at", desc=True).execute().data or [], True
    except Exception:
        return [], False


def fmt(x) -> str:
    return f"{x:,.0f}".replace(",", " ") + " сом"


def _supplier_users():
    try:
        return supabase.table("users").select("id, username").eq("role", SUPPLIER_ROLE).execute().data or []
    except Exception:
        return []


def _admin_supplier_block():
    users = _supplier_users()
    with st.expander("👤 Логин поставщика" + (f" ({', '.join(u['username'] for u in users)})" if users else " — не создан")):
        if users:
            st.caption("Поставщик входит через боковое меню → «🔑 Вход по логину».")
        with st.form("create_supplier_user", clear_on_submit=True):
            st.write("Создать логин для поставщика")
            uname = st.text_input("Логин", value="" if users else "ikrom")
            pwd = st.text_input("Пароль", type="password")
            if st.form_submit_button("Создать"):
                if not uname.strip() or len(pwd) < 4:
                    st.error("Введите логин и пароль (не короче 4 символов)")
                elif any(u["username"] == uname.strip() for u in users):
                    st.error("Такой логин уже есть")
                elif create_new_user(uname, pwd, SUPPLIER_ROLE):
                    st.success(f"Логин «{uname.strip()}» создан. Передайте его поставщику вместе с паролем.")


def show_supplier_debt_page():
    user = st.session_state.get("user") or {}
    role = user.get("role", "Кассир")
    side = side_of_role(role)
    st.header("🤝 Долг с поставщиком (Икром)")

    entries, ok = load_entries()
    if not ok:
        st.warning(MIGRATION_HINT)
        if is_admin(role):
            try:
                st.code(open("migrations/005_supplier_debt.sql", encoding="utf-8").read(), language="sql")
            except Exception:
                pass
        return

    if is_admin(role):
        _admin_supplier_block()

    debt = balance(entries)
    pend = pending_balance(entries)
    if debt > 0:
        st.metric("Магазин должен поставщику", fmt(debt))
    elif debt < 0:
        st.metric("Поставщик должен магазину (переплата)", fmt(-debt))
    else:
        st.metric("Долг сейчас", "0 сом")
    n_pending = sum(1 for e in entries if not e.get("accepted"))
    if n_pending:
        st.caption(f"⏳ Ждут подтверждения: {n_pending} (на {fmt(abs(pend))}) — в долг пока не входят.")

    # --- Новая запись ---
    st.subheader("➕ Новая запись")
    types = allowed_types(side)
    with st.form("supplier_new_entry", clear_on_submit=True):
        op = st.radio("Что произошло", types, format_func=lambda t: TYPE_LABELS[t], horizontal=True)
        amount = st.number_input("Сумма, сом", min_value=0.0, step=100.0)
        comment = st.text_input("Комментарий (необязательно)")
        if st.form_submit_button("Сохранить", type="primary", width="stretch"):
            if op not in types:
                st.error("Эту операцию создаёт другая сторона")
            elif not validate_amount(amount):
                st.error("Введите сумму больше нуля")
            else:
                supabase.table("supplier_ledger").insert({
                    "type": op, "amount": float(amount), "comment": comment.strip() or None,
                    "created_by_user_id": user.get("id") or None, "created_by_name": user.get("username"),
                    "created_by_role": role, "created_by_side": side,
                }).execute()
                st.success("Сохранено. Ждём подтверждения другой стороны.")
                st.rerun()

    # --- Ожидают моего подтверждения ---
    to_accept = [e for e in entries if can_accept(e, side)]
    mine_pending = [e for e in entries if can_delete_entry(e, side)]
    if to_accept:
        st.subheader("✅ Подтвердите")
        for e in to_accept:
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{TYPE_LABELS.get(e['type'], e['type'])}** — {fmt(float(e['amount']))} · "
                     f"{str(e.get('created_at', ''))[:10]} · {e.get('created_by_name') or ''}"
                     + (f" · _{e['comment']}_" if e.get("comment") else ""))
            if c2.button("Принял", key=f"acc_{e['id']}", type="primary", width="stretch"):
                supabase.table("supplier_ledger").update({
                    "accepted": True, "accepted_at": datetime.now(timezone.utc).isoformat(),
                    "accepted_by_user_id": user.get("id") or None, "accepted_by_name": user.get("username"),
                }).eq("id", e["id"]).eq("accepted", False).execute()
                st.rerun()
    if mine_pending:
        with st.expander(f"⏳ Мои записи без подтверждения ({len(mine_pending)})"):
            for e in mine_pending:
                c1, c2 = st.columns([3, 1])
                c1.write(f"{TYPE_LABELS.get(e['type'], e['type'])} — {fmt(float(e['amount']))} · {str(e.get('created_at', ''))[:10]}")
                if c2.button("Отменить", key=f"del_{e['id']}", width="stretch"):
                    supabase.table("supplier_ledger").delete().eq("id", e["id"]).eq("accepted", False).execute()
                    st.rerun()

    # --- История ---
    st.subheader("📜 История")
    if not entries:
        st.info("Записей пока нет")
        return
    rows = [{
        "Дата": str(e.get("created_at", ""))[:16].replace("T", " "),
        "Тип": TYPE_LABELS.get(e.get("type"), e.get("type")),
        "Сумма": float(e.get("amount") or 0),
        "Кто внёс": e.get("created_by_name") or e.get("created_by_side") or "",
        "Принято": "✅" if e.get("accepted") else "⏳",
        "Кто принял": e.get("accepted_by_name") or "",
        "Комментарий": e.get("comment") or "",
    } for e in entries]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
