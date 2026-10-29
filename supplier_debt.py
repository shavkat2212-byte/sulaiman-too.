# Магазин «Сулайман-Тоо» — Модуль: Долг с поставщиком (Икром). Только суммы, без фото.
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from database import supabase, create_new_user
from supplier_logic import (
    SUPPLIER_ROLE, TYPES, TYPE_GOODS, TYPE_PAYMENT, TYPE_RETURN,
    side_of_role, allowed_types, can_accept, can_delete_entry, balance, pending_balance, validate_amount,
    SHOP, SUPPLIER, parse_lines, lines_sum, can_create_order, can_confirm_order, can_accept_order,
    can_cancel_order, next_status, ledger_from_order, ORDER_SENT, ORDER_CONFIRMED,
)
from stock_logic import is_admin
from supplier_month import show_monthly_grid

TYPE_LABELS = {TYPE_GOODS: "📦 Товар пришёл", TYPE_PAYMENT: "💸 Оплата", TYPE_RETURN: "↩️ Возврат"}

MIGRATION_HINT = (
    "Таблица учёта долга ещё не создана. Администратору нужно один раз выполнить файл "
    "`migrations/005_supplier_debt.sql` в Supabase → SQL Editor → Run."
)
MIGRATION_HINT_006 = (
    "Списки товаров и заказы ещё не включены. Администратору нужно один раз выполнить файл "
    "`migrations/006_supplier_orders.sql` в Supabase → SQL Editor → Run."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_lines(table, fk):
    """{parent_id: [lines]} или None, если таблицы нет (миграция 006 не выполнена)."""
    try:
        data = supabase.table(table).select("*").order("id").execute().data or []
    except Exception:
        return None
    out = {}
    for l in data:
        out.setdefault(l[fk], []).append(l)
    return out


def load_orders():
    try:
        return supabase.table("supplier_orders").select("*").order("created_at", desc=True).execute().data or []
    except Exception:
        return None


def _lines_editor(key, with_price=True, with_note=False, initial=None):
    cols = {"Товар": [""] * 5, "Кол-во": [None] * 5}
    if with_price:
        cols["Цена"] = [None] * 5
    if with_note:
        cols["Примечание"] = [""] * 5
    df = pd.DataFrame(initial) if initial else pd.DataFrame(cols)
    cfg = {"Товар": st.column_config.TextColumn("Товар"),
           "Кол-во": st.column_config.NumberColumn("Кол-во", min_value=0, step=1)}
    if with_price:
        cfg["Цена"] = st.column_config.NumberColumn("Цена, сом", min_value=0.0, step=10.0)
    ed = st.data_editor(df, num_rows="dynamic", width="stretch", hide_index=True, key=key, column_config=cfg)
    return parse_lines(ed.to_dict("records"))


def _show_lines(lines, title="Товары"):
    if not lines:
        return
    rows = [{"Товар": l.get("name"), "Кол-во": l.get("qty"), "Цена": l.get("unit_price"),
             "Сумма": l.get("line_total"), "Примечание": l.get("note") or ""} for l in lines]
    df = pd.DataFrame(rows).dropna(axis=1, how="all")
    st.caption(title)
    st.dataframe(df, width="stretch", hide_index=True)


def _save_lines(table, fk, parent_id, lines):
    if lines:
        supabase.table(table).insert([{fk: parent_id, "name": l["name"], "qty": l.get("qty"),
                                       "unit_price": l.get("unit_price"), "line_total": l.get("line_total"),
                                       "note": l.get("note")} for l in lines]).execute()


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

    ledger_lines = load_lines("supplier_ledger_lines", "ledger_id")
    orders = load_orders()
    has_006 = ledger_lines is not None and orders is not None
    if not has_006:
        st.info(MIGRATION_HINT_006)
        if is_admin(role):
            try:
                with st.expander("SQL для миграции 006"):
                    st.code(open("migrations/006_supplier_orders.sql", encoding="utf-8").read(), language="sql")
            except Exception:
                pass
        ledger_lines, orders = {}, []

    open_orders = [o for o in orders if o.get("status") in (ORDER_SENT, ORDER_CONFIRMED)]
    tab_grid, tab_debt, tab_orders, tab_hist = st.tabs(
        ["📊 Таблица по месяцам", "✅ Записи с подтверждением",
         f"📝 Заказы ({len(open_orders)})" if open_orders else "📝 Заказы", "📜 История"])
    with tab_grid:
        show_monthly_grid(user, can_edit=True)
    with tab_debt:
        st.caption("Старый учёт с взаимным подтверждением (отдельно от таблицы по месяцам).")
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
        _debt_tab(user, role, side, entries, ledger_lines, has_006)
    with tab_orders:
        if has_006:
            _orders_tab(user, side, orders)
        else:
            st.info(MIGRATION_HINT_006)
    with tab_hist:
        _history_tab(entries, ledger_lines, is_admin(role))


def _debt_tab(user, role, side, entries, ledger_lines, has_006):
    st.subheader("➕ Новая запись")
    types = allowed_types(side)
    op = st.radio("Что произошло", types, format_func=lambda t: TYPE_LABELS[t], horizontal=True, key="sup_op")
    lines = []
    if has_006 and op in (TYPE_GOODS, TYPE_RETURN):
        st.caption("Список товаров (по желанию — чтобы другая сторона видела, что именно):")
        lines = _lines_editor(f"sup_lines_{op}")
        if lines_sum(lines):
            st.caption(f"Сумма по строкам: {fmt(lines_sum(lines))}")
    amount = st.number_input("Итого сумма, сом (идёт в долг)", min_value=0.0, step=100.0,
                             value=float(lines_sum(lines)), key=f"sup_amount_{op}")
    comment = st.text_input("Комментарий (необязательно)", key=f"sup_comment_{op}")
    if st.button("Сохранить", type="primary", width="stretch", key="sup_save"):
        if op not in types:
            st.error("Эту операцию создаёт другая сторона")
        elif not validate_amount(amount):
            st.error("Введите итоговую сумму больше нуля")
        else:
            res = supabase.table("supplier_ledger").insert({
                "type": op, "amount": float(amount), "comment": comment.strip() or None,
                "created_by_user_id": user.get("id") or None, "created_by_name": user.get("username"),
                "created_by_role": role, "created_by_side": side,
            }).execute()
            if lines and res.data:
                _save_lines("supplier_ledger_lines", "ledger_id", res.data[0]["id"], lines)
            for k in (f"sup_lines_{op}", f"sup_amount_{op}", f"sup_comment_{op}"):
                st.session_state.pop(k, None)
            st.success("Сохранено. Ждём подтверждения другой стороны.")
            st.rerun()

    to_accept = [e for e in entries if can_accept(e, side)]
    mine_pending = [e for e in entries if can_delete_entry(e, side)]
    if to_accept:
        st.subheader("✅ Подтвердите")
        for e in to_accept:
            with st.container(border=True):
                st.write(f"**{TYPE_LABELS.get(e['type'], e['type'])}** — {fmt(float(e['amount']))} · "
                         f"{str(e.get('created_at', ''))[:10]} · {e.get('created_by_name') or ''}"
                         + (f" · _{e['comment']}_" if e.get("comment") else ""))
                _show_lines(ledger_lines.get(e["id"]))
                if st.button("Принял", key=f"acc_{e['id']}", type="primary", width="stretch"):
                    supabase.table("supplier_ledger").update({
                        "accepted": True, "accepted_at": _now(),
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


def _orders_tab(user, side, orders):
    order_lines = load_lines("supplier_order_lines", "order_id") or {}
    if can_create_order(side):
        with st.expander("➕ Новый заказ поставщику", expanded=not orders):
            lines = _lines_editor("order_new_lines", with_price=False, with_note=True)
            comment = st.text_input("Комментарий к заказу", key="order_new_comment")
            if st.button("📤 Отправить заказ", type="primary", width="stretch", key="order_send"):
                if not lines:
                    st.error("Добавьте хотя бы один товар")
                else:
                    res = supabase.table("supplier_orders").insert({
                        "status": ORDER_SENT, "comment": comment.strip() or None,
                        "created_by_user_id": user.get("id") or None, "created_by_name": user.get("username"),
                    }).execute()
                    if res.data:
                        _save_lines("supplier_order_lines", "order_id", res.data[0]["id"], lines)
                    for k in ("order_new_lines", "order_new_comment"):
                        st.session_state.pop(k, None)
                    st.success("Заказ отправлен поставщику")
                    st.rerun()

    if not orders:
        st.info("Заказов пока нет")
        return
    for o in orders:
        status = o.get("status")
        icon = {"отправлен": "📤", "подтверждён": "✅", "принят": "📦", "отменён": "❌"}.get(status, "")
        amt = f" · {fmt(float(o['confirmed_amount']))}" if o.get("confirmed_amount") else ""
        active = status in (ORDER_SENT, ORDER_CONFIRMED)
        with st.expander(f"{icon} Заказ №{o['id']} · {str(o.get('created_at', ''))[:10]} · {status}{amt}", expanded=active):
            if o.get("comment"):
                st.write(f"Комментарий: _{o['comment']}_")
            _show_lines(order_lines.get(o["id"]), "Что заказано")
            if o.get("supplier_comment"):
                st.write(f"Поставщик: _{o['supplier_comment']}_")
            if can_confirm_order(o, side):
                amount = st.number_input("Итого сумма, сом", min_value=0.0, step=100.0,
                                         value=float(o.get("confirmed_amount") or 0), key=f"oc_amt_{o['id']}")
                scomm = st.text_input("Комментарий (необязательно)", value=o.get("supplier_comment") or "",
                                      key=f"oc_com_{o['id']}")
                if st.button("✅ Подтвердить сумму", type="primary", width="stretch", key=f"oc_btn_{o['id']}"):
                    if not validate_amount(amount):
                        st.error("Введите сумму больше нуля")
                    else:
                        supabase.table("supplier_orders").update({
                            "status": next_status(o, "confirm", side), "confirmed_amount": float(amount),
                            "confirmed_at": _now(), "confirmed_by_name": user.get("username"),
                            "supplier_comment": scomm.strip() or None,
                        }).eq("id", o["id"]).in_("status", [ORDER_SENT, ORDER_CONFIRMED]).execute()
                        st.rerun()
            if can_accept_order(o, side):
                if st.button(f"📦 Принять — {fmt(float(o['confirmed_amount']))} в долг", type="primary",
                             width="stretch", key=f"oa_btn_{o['id']}"):
                    upd = supabase.table("supplier_orders").update({
                        "status": next_status(o, "accept", side), "accepted_at": _now(),
                        "accepted_by_name": user.get("username"),
                    }).eq("id", o["id"]).eq("status", ORDER_CONFIRMED).execute()
                    if upd.data:
                        led = ledger_from_order(o)
                        led.update({"created_by_user_id": user.get("id") or None,
                                    "created_by_name": o.get("confirmed_by_name") or "поставщик",
                                    "created_by_role": SUPPLIER_ROLE, "created_by_side": SUPPLIER,
                                    "accepted_at": _now(), "accepted_by_user_id": user.get("id") or None,
                                    "accepted_by_name": user.get("username")})
                        res = supabase.table("supplier_ledger").insert(led).execute()
                        if res.data:
                            lid = res.data[0]["id"]
                            supabase.table("supplier_orders").update({"ledger_id": lid}).eq("id", o["id"]).execute()
                            _save_lines("supplier_ledger_lines", "ledger_id", lid, order_lines.get(o["id"]) or [])
                    st.rerun()
            if can_cancel_order(o, side):
                if st.button("Отменить заказ", key=f"ox_btn_{o['id']}", width="stretch"):
                    supabase.table("supplier_orders").update({
                        "status": next_status(o, "cancel", side), "cancelled_at": _now(),
                        "cancelled_by_name": user.get("username"),
                    }).eq("id", o["id"]).in_("status", [ORDER_SENT, ORDER_CONFIRMED]).execute()
                    st.rerun()


def _history_tab(entries, ledger_lines, admin=False):
    if not entries:
        st.info("Записей пока нет")
        return
    rows = [{
        "Дата": str(e.get("created_at", ""))[:16].replace("T", " "),
        "Тип": TYPE_LABELS.get(e.get("type"), e.get("type")),
        "Сумма": float(e.get("amount") or 0),
        "Товаров": len(ledger_lines.get(e["id"]) or []) or "",
        "Кто внёс": e.get("created_by_name") or e.get("created_by_side") or "",
        "Принято": "✅" if e.get("accepted") else "⏳",
        "Кто принял": e.get("accepted_by_name") or "",
        "Комментарий": e.get("comment") or "",
    } for e in entries]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    with_lines = [e for e in entries if ledger_lines.get(e["id"])]
    if with_lines:
        opts = {f"{str(e.get('created_at', ''))[:10]} · {TYPE_LABELS.get(e['type'], e['type'])} · {fmt(float(e['amount']))}": e["id"]
                for e in with_lines}
        sel = st.selectbox("Посмотреть список товаров записи", list(opts.keys()), key="hist_sel")
        _show_lines(ledger_lines.get(opts[sel]))
