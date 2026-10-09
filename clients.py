# Магазин «Сулайман-Тоо» — Модуль: Клиенты и рассрочки
# Версия: 1.11 (пересоздание графика не трогает оплаченные платежи)

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase
import os


def parse_due(value):
    if not value:
        return None
    text = str(value)[:10]
    if ".00." in text:
        text = text.replace(".00.", f".{datetime.now().strftime('%m')}.")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def add_months(start_date, months, pay_day):
    year = start_date.year
    month = start_date.month + months
    while month > 12:
        month -= 12
        year += 1
    day = min(int(pay_day), 28)
    return datetime(year, month, day).date()


def show_clients_page():
    st.title("👥 Клиенты и рассрочки")
    user_role = st.session_state.get("user", {}).get("role", "Кассир")

    tab_work, tab_base, tab_extra = st.tabs([
        "💳 Рассрочки",
        "🗂️ База клиентов",
        "📄 Аналитика и договор",
    ])

    try:
        clients = supabase.table("clients").select("*").order("fio").execute().data or []
        sales = supabase.table("sales").select("*").eq("payment", "Рассрочка").execute().data or []
        payments = supabase.table("credit_payments").select("*").execute().data or []
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return

    clients_map = {c["id"]: c for c in clients}
    today = datetime.now().date()

    with tab_work:
        show_work_tab(user_role, clients, clients_map, sales, payments, today)
    with tab_base:
        show_base_tab(clients)
    with tab_extra:
        show_extra_tab(user_role, clients, clients_map, sales, payments)


def show_work_tab(user_role, clients, clients_map, sales, payments, today):
    st.subheader("Кто должен и приём оплаты")

    by_client = {}
    for sale in sales:
        cid = sale.get("client_id")
        if not cid:
            continue
        sale_pays = [p for p in payments if p.get("sale_id") == sale.get("id")]
        paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_pays)
        balance = float(sale.get("credit_balance", 0) or 0)
        debt = balance - paid
        unpaid = [p for p in sale_pays if float(p.get("amount_expected", 0) or 0) - float(p.get("amount_paid", 0) or 0) > 0.5]
        unpaid = sorted(unpaid, key=lambda p: parse_due(p.get("due_date")) or today)
        next_due = parse_due(unpaid[0].get("due_date")) if unpaid else None
        next_left = 0.0
        if unpaid:
            next_left = float(unpaid[0].get("amount_expected", 0) or 0) - float(unpaid[0].get("amount_paid", 0) or 0)

        item = by_client.setdefault(cid, {
            "debt": 0.0,
            "next_due": None,
            "next_left": 0.0,
            "sales": [],
        })
        item["debt"] += debt
        item["sales"].append(sale)
        if next_due and (item["next_due"] is None or next_due < item["next_due"]):
            item["next_due"] = next_due
            item["next_left"] = next_left

    rows = []
    for cid, item in by_client.items():
        if item["debt"] <= 0.5:
            continue
        client = clients_map.get(cid, {})
        due = item["next_due"]
        if due and due < today:
            status = "🔴 Просрочка"
        elif due and due == today:
            status = "🟡 Сегодня"
        else:
            status = "⚪ Позже"
        rows.append({
            "id": cid,
            "fio": client.get("fio", "Неизвестный"),
            "phone": client.get("phone") or "—",
            "debt": item["debt"],
            "next_due": due,
            "next_left": item["next_left"],
            "status": status,
        })

    rows.sort(key=lambda r: (r["next_due"] or datetime.max.date(), r["fio"]))

    search = st.text_input("Поиск по фамилии или телефону", key="credit_search")
    if search:
        q = search.strip().lower()
        rows = [r for r in rows if q in r["fio"].lower() or q in str(r["phone"])]

    left, right = st.columns([1.15, 1.4])
    with left:
        st.markdown(f"**Клиентов с долгом: {len(rows)}**")
        if not rows:
            st.info("Активных долгов нет.")
        else:
            labels = {}
            for r in rows:
                due_txt = r["next_due"].strftime("%d.%m.%Y") if r["next_due"] else "—"
                label = f"{r['status']} | {r['fio']} | {int(r['debt']):,} сом | {due_txt}"
                labels[label] = r
            picked = st.radio("Выберите клиента", list(labels.keys()), key="credit_client_pick")
            st.session_state["picked_credit_client"] = labels[picked]["id"]

    with right:
        cid = st.session_state.get("picked_credit_client")
        if not cid or cid not in by_client:
            st.info("Выберите клиента слева.")
            return

        client = clients_map.get(cid, {})
        st.markdown(f"### {client.get('fio', 'Клиент')}")
        st.caption(f"Телефон: {client.get('phone') or '—'} | Остаток: **{int(by_client[cid]['debt']):,} сом**")
        st.button(
            "📱 Выписка для клиента (скриншот)",
            use_container_width=True,
            on_click=open_client_statement,
            args=(cid,),
            key="open_statement_btn",
        )

        client_sales = [s for s in sales if s.get("client_id") == cid]
        sale_labels = {}
        for s in client_sales:
            sale_pays = [p for p in payments if p.get("sale_id") == s.get("id")]
            paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_pays)
            debt = float(s.get("credit_balance", 0) or 0) - paid
            if debt <= 0.5:
                continue
            label = f"{str(s.get('name', ''))[:55]} | долг {int(debt):,}"
            sale_labels[label] = s

        if not sale_labels:
            st.success("По этому клиенту долга уже нет.")
            return

        sale_label = st.selectbox("Договор", list(sale_labels.keys()), key="credit_sale_pick")
        sale = sale_labels[sale_label]
        sale_pays = [p for p in payments if p.get("sale_id") == sale.get("id")]
        unpaid = [
            p for p in sale_pays
            if float(p.get("amount_expected", 0) or 0) - float(p.get("amount_paid", 0) or 0) > 0.5
        ]
        unpaid = sorted(unpaid, key=lambda p: parse_due(p.get("due_date")) or today)

        pay_labels = {}
        for p in unpaid:
            due = parse_due(p.get("due_date"))
            left_amt = float(p.get("amount_expected", 0) or 0) - float(p.get("amount_paid", 0) or 0)
            due_txt = due.strftime("%d.%m.%Y") if due else "—"
            mark = "просрочка" if due and due < today else ("сегодня" if due == today else "")
            label = f"{due_txt} | осталось {int(left_amt):,} сом {mark}".strip()
            pay_labels[label] = p

        if not pay_labels:
            st.info("Неоплаченных месяцев нет.")
            return

        pay_label = st.selectbox("Куда зачислить", list(pay_labels.keys()), key="credit_pay_pick")
        target = pay_labels[pay_label]
        left_amt = float(target.get("amount_expected", 0) or 0) - float(target.get("amount_paid", 0) or 0)

        amount = st.number_input(
            "Сумма оплаты, сом",
            min_value=0.0,
            value=float(int(left_amt)),
            step=100.0,
            key=f"accept_amount_{target['id']}",
        )
        st.caption("Если сумма больше этого месяца, остаток сам уйдёт на следующие платежи.")
        if st.button("💳 Принять оплату", type="primary", use_container_width=True):
            accept_payment(unpaid, amount, client.get("fio", "клиент"), target["id"])

        with st.expander("График этого договора"):
            show_rows = []
            for p in sorted(sale_pays, key=lambda x: parse_due(x.get("due_date")) or today):
                due = parse_due(p.get("due_date"))
                show_rows.append({
                    "Дата": due.strftime("%d.%m.%Y") if due else str(p.get("due_date")),
                    "Ожидается": int(float(p.get("amount_expected", 0) or 0)),
                    "Оплачено": int(float(p.get("amount_paid", 0) or 0)),
                    "Статус": p.get("status", ""),
                })
            st.dataframe(pd.DataFrame(show_rows), use_container_width=True, hide_index=True)

        if user_role == "Администратор":
            st.markdown("---")
            st.markdown("**Правка графика (админ)**")
            new_day = st.number_input("Поставить оставшиеся платежи на число", min_value=1, max_value=28, value=10, key="shift_day")
            if st.button("Сдвинуть оставшиеся на это число"):
                shift_remaining(unpaid, int(new_day))

            if unpaid:
                edit_p = pay_labels[pay_label]
                due = parse_due(edit_p.get("due_date")) or today
                new_due = st.date_input("Дата выбранного платежа", value=due, key=f"one_due_{edit_p['id']}")
                new_expected = st.number_input(
                    "Сумма выбранного платежа",
                    min_value=0.0,
                    value=float(edit_p.get("amount_expected", 0) or 0),
                    step=50.0,
                    key=f"one_amt_{edit_p['id']}",
                )
                if st.button("Сохранить дату и сумму"):
                    supabase.table("credit_payments").update({
                        "due_date": new_due.strftime("%Y-%m-%d"),
                        "amount_expected": new_expected,
                    }).eq("id", edit_p["id"]).execute()
                    st.success("Платёж обновлён")
                    st.rerun()

            open_count = len([p for p in sale_pays if float(p.get("amount_paid", 0) or 0) <= 0.5])
            months = st.number_input("Разложить неоплаченный остаток на месяцев", min_value=1, max_value=36,
                                     value=max(open_count, 1), key="rebuild_months")
            if st.button(
                "Пересоздать неоплаченные платежи с текущего месяца",
                help="Оплаченные и частично оплаченные платежи не меняются. Неоплаченные раскладываются заново "
                     "поровну, чтобы весь график = сумме рассрочки по договору. Изменения пишутся в журнал.",
            ):
                rebuild_schedule(sale, sale_pays, int(months))


def open_client_statement(client_id):
    try:
        from statement import open_statement
        open_statement(client_id)
    except Exception:
        pass


def accept_payment(unpaid, amount, client_name, start_id):
    if amount <= 0:
        st.error("Введите сумму больше 0")
        return
    ordered = unpaid[:]
    start = next((i for i, p in enumerate(ordered) if p["id"] == start_id), 0)
    ordered = ordered[start:]
    left_to_apply = float(amount)
    applied = 0.0
    for p in ordered:
        if left_to_apply <= 0:
            break
        expected = float(p.get("amount_expected", 0) or 0)
        paid = float(p.get("amount_paid", 0) or 0)
        room = expected - paid
        if room <= 0:
            continue
        take = min(room, left_to_apply)
        new_paid = paid + take
        status = "Оплачен" if new_paid + 0.5 >= expected else "Частично"
        supabase.table("credit_payments").update({
            "amount_paid": new_paid,
            "status": status,
        }).eq("id", p["id"]).execute()
        left_to_apply -= take
        applied += take

    if applied <= 0:
        st.error("Некуда зачислить оплату")
        return

    now_fmt = datetime.now().strftime("%d.%m.%Y %H:%M")
    supabase.table("cash_operations").insert({
        "date": now_fmt,
        "amount": applied,
        "comment": f"Погашение рассрочки от {client_name}",
    }).execute()
    extra = amount - applied
    if extra > 0.5:
        st.warning(f"Принято {int(applied)} сом. Лишние {int(extra)} сом некуда зачислить — долг закрыт.")
    else:
        st.success(f"Принято {int(applied)} сом от {client_name}")
    st.rerun()


def shift_remaining(unpaid, pay_day):
    for p in unpaid:
        due = parse_due(p.get("due_date")) or datetime.now().date()
        new_due = datetime(due.year, due.month, min(pay_day, 28)).date()
        supabase.table("credit_payments").update({
            "due_date": new_due.strftime("%Y-%m-%d")
        }).eq("id", p["id"]).execute()
    st.success("Даты оставшихся платежей обновлены")
    st.rerun()


def rebuild_schedule(sale, sale_pays, months):
    """Пересобирает только неоплаченные строки; оплаченные и частичные не трогает."""
    from installment_logic import plan_rebuild_unpaid
    from installment_admin import NotAdmin, apply_schedule_plan, audit_available
    try:
        plan = plan_rebuild_unpaid(sale, sale_pays, months, datetime.now().date())
    except ValueError as e:
        st.error(str(e))
        return
    if plan["errors"]:
        st.error("; ".join(plan["errors"]))
        return
    if not audit_available():
        st.error("Журнал audit_log недоступен — выполните migrations/001_audit_log.sql в Supabase и повторите.")
        return
    try:
        apply_schedule_plan(sale, plan, f"Пересоздание неоплаченных платежей на {months} мес.")
    except NotAdmin as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Ошибка: {e}. Обновите страницу и проверьте график.")
        return
    st.success("Неоплаченные платежи пересозданы, оплаченные не тронуты")
    st.rerun()


def show_base_tab(clients):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Новый клиент")
        with st.form("client_reg", clear_on_submit=True):
            fio = st.text_input("ФИО").strip()
            phone = st.text_input("Телефон").strip()
            address = st.text_input("Адрес").strip()
            passport = st.text_area("Паспорт").strip()
            if st.form_submit_button("Зарегистрировать"):
                if fio:
                    supabase.table("clients").insert({
                        "fio": fio,
                        "phone": phone or None,
                        "address": address or None,
                        "passport": passport or None,
                    }).execute()
                    st.success("Клиент добавлен")
                    st.rerun()
    with col2:
        st.subheader("Изменить клиента")
        if clients:
            opts = {c["fio"]: c for c in clients}
            name = st.selectbox("Клиент", list(opts.keys()))
            person = opts[name]
            with st.form("client_edit_form"):
                new_fio = st.text_input("ФИО", value=str(person.get("fio") or ""))
                new_phone = st.text_input("Телефон", value=str(person.get("phone") or ""))
                new_address = st.text_input("Адрес", value=str(person.get("address") or ""))
                new_passport = st.text_area("Паспорт", value=str(person.get("passport") or ""))
                if st.form_submit_button("Сохранить"):
                    supabase.table("clients").update({
                        "fio": new_fio.strip(),
                        "phone": new_phone.strip() or None,
                        "address": new_address.strip() or None,
                        "passport": new_passport.strip() or None,
                    }).eq("id", person["id"]).execute()
                    st.success("Сохранено")
                    st.rerun()
    if clients:
        df = pd.DataFrame(clients).drop(columns=["created_at"], errors="ignore")
        st.dataframe(df, use_container_width=True, hide_index=True)


def show_extra_tab(user_role, clients, clients_map, sales, payments):
    st.subheader("Активные договоры")
    rows = []
    for s in sales:
        sale_pays = [p for p in payments if p.get("sale_id") == s.get("id")]
        paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_pays)
        balance = float(s.get("credit_balance", 0) or 0)
        debt = balance - paid
        if debt <= 0.5:
            continue
        rows.append({
            "Клиент": clients_map.get(s.get("client_id"), {}).get("fio", "Неизвестный"),
            "Договор": str(s.get("name", ""))[:70],
            "Закупка": int(s.get("total_cost", 0) or 0),
            "Продажа": int(s.get("total_sale", 0) or 0),
            "Взнос": int(s.get("down_payment", 0) or 0),
            "Долг + наценка": int(balance),
            "Остаток": int(debt),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Активных рассрочек нет.")

    st.markdown("---")
    st.subheader("Скачать договор")
    if not sales:
        return
    sale_opts = {
        f"{clients_map.get(s.get('client_id'), {}).get('fio', '')} | {str(s.get('name', ''))[:40]}": s
        for s in sales
    }
    label = st.selectbox("Договор", list(sale_opts.keys()), key="contract_pick")
    sale = sale_opts[label]
    client = clients_map.get(sale.get("client_id"), {})
    sale_pays = [p for p in payments if p.get("sale_id") == sale.get("id")]
    months = len(sale_pays) or 6
    if st.button("Сформировать Word"):
        try:
            from contract_generator import fill_contract, generate_payment_schedule
            if not os.path.exists("contract_template.docx"):
                st.error("Нет файла contract_template.docx")
                return
            down = float(sale.get("down_payment", 0) or 0)
            credit = float(sale.get("credit_balance", 0) or 0)
            total = down + credit if credit > 0 else float(sale.get("total_sale", 0) or 0)
            schedule = generate_payment_schedule(total, down, months)
            doc = fill_contract(
                template_path="contract_template.docx",
                contract_number=str(sale.get("id", "б/н")),
                contract_date=datetime.now().strftime("%d.%m.%Y"),
                client_name=client.get("fio", ""),
                client_address=client.get("address") or "—",
                client_passport=client.get("passport") or "—",
                total_amount=total,
                months=months,
                product_name=sale.get("name", "Товар"),
                product_qty=int(sale.get("qty", 1) or 1),
                product_price=total,
                down_payment=down,
                schedule=schedule,
            )
            st.download_button(
                "Скачать договор",
                data=doc,
                file_name=f"Dogovor_{client.get('fio', 'client')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except Exception as e:
            st.error(f"Ошибка договора: {e}")
