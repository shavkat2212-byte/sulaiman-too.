# Магазин «Сулайман-Тоо» — Модуль: Клиенты и рассрочки
# Версия: 1.15 (быстрая оплата: один договор и ближайший месяц выбираются сами; пустые selectbox, передача договора другому клиенту, правки без обязательного журнала)

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


RECEIPT_KEY = "payment_receipt"


def client_debts(sales, payments, today):
    by_client = {}
    for sale in sales:
        cid = sale.get("client_id")
        if not cid:
            continue
        sale_pays = [p for p in payments if p.get("sale_id") == sale.get("id")]
        paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_pays)
        debt = float(sale.get("credit_balance", 0) or 0) - paid
        unpaid = [p for p in sale_pays if float(p.get("amount_expected", 0) or 0) - float(p.get("amount_paid", 0) or 0) > 0.5]
        unpaid = sorted(unpaid, key=lambda p: parse_due(p.get("due_date")) or today)
        next_due = parse_due(unpaid[0].get("due_date")) if unpaid else None
        next_left = 0.0
        if unpaid:
            next_left = float(unpaid[0].get("amount_expected", 0) or 0) - float(unpaid[0].get("amount_paid", 0) or 0)
        item = by_client.setdefault(cid, {"debt": 0.0, "next_due": None, "next_left": 0.0, "sales": []})
        item["debt"] += debt
        item["sales"].append(sale)
        if next_due and (item["next_due"] is None or next_due < item["next_due"]):
            item["next_due"] = next_due
            item["next_left"] = next_left
    return by_client


def show_work_tab(user_role, clients, clients_map, sales, payments, today):
    st.subheader("Приём оплаты")
    if st.session_state.get("inst_flash"):
        st.success(st.session_state.pop("inst_flash"))
    by_client = client_debts(sales, payments, today)

    rows = []
    for cid, item in by_client.items():
        if item["debt"] <= 0.5:
            continue
        client = clients_map.get(cid, {})
        due = item["next_due"]
        if due and due < today:
            status = "🔴"
        elif due and due == today:
            status = "🟡"
        else:
            status = "⚪"
        rows.append({"id": cid, "fio": client.get("fio", "Неизвестный"), "phone": client.get("phone") or "—",
                     "debt": item["debt"], "next_due": due, "next_left": item["next_left"], "status": status})
    rows.sort(key=lambda r: (r["next_due"] or datetime.max.date(), r["fio"]))

    receipt = st.session_state.get(RECEIPT_KEY)
    # клиент, которому только что приняли оплату, остаётся в списке, даже если долг закрыт
    if receipt and receipt.get("client_id") in clients_map and not any(r["id"] == receipt["client_id"] for r in rows):
        c = clients_map[receipt["client_id"]]
        rows.insert(0, {"id": c["id"], "fio": c.get("fio", ""), "phone": c.get("phone") or "—", "debt": 0.0,
                        "next_due": None, "next_left": 0.0, "status": "✅"})

    search = st.text_input("Поиск по фамилии или телефону", key="credit_search")
    if search:
        q = search.strip().lower()
        rows = [r for r in rows if q in r["fio"].lower() or q in str(r["phone"])]
    if not rows:
        st.info("Активных долгов нет." if not search else "Клиент не найден.")
        return

    # значения — id (не текст с суммой), чтобы выбор не сбрасывался, когда после оплаты меняется долг
    labels = {}
    for r in rows:
        due_txt = r["next_due"].strftime("%d.%m.%Y") if r["next_due"] else "—"
        labels[r["id"]] = f"{r['status']} {r['fio']} · {int(r['debt']):,} сом · {due_txt}".replace(",", " ")
    st.caption(f"Клиентов с долгом: {len(rows)}. 🔴 просрочка · 🟡 сегодня · ⚪ позже")
    if search and len(rows) == 1:
        # поиск нашёл ровно одного клиента — выбираем его сразу
        cid = rows[0]["id"]
        st.session_state["credit_client_pick"] = cid
        st.caption(f"Клиент: {labels[cid]}")
    else:
        client_options = [None] + list(labels.keys())
        def client_format(i):
            if i is None:
                return "— Выберите клиента —"
            return labels.get(i, str(i))
        if st.session_state.get("credit_client_pick") not in client_options:
            st.session_state["credit_client_pick"] = None
        cid = st.selectbox("Клиент", client_options, format_func=client_format, key="credit_client_pick")
    if cid is None:
        st.info("Выберите клиента для оплаты.")
        return

    # При смене клиента очищаем выбор договора и платежа
    if st.session_state.get("credit_bound_client") != cid:
        st.session_state.pop("credit_sale_pick", None)
        st.session_state.pop("credit_pay_pick", None)
        st.session_state["credit_bound_client"] = cid

    st.session_state["picked_credit_client"] = cid
    client = clients_map.get(cid, {})

    if receipt and receipt.get("client_id") != cid:
        st.session_state.pop(RECEIPT_KEY, None)  # выбрали другого клиента — квитанцию убираем
        receipt = None

    if receipt:
        show_receipt(receipt, client, cid, sales, payments, today)

    debt_now = by_client.get(cid, {}).get("debt", 0.0)
    st.markdown(f"**{client.get('fio', 'Клиент')}** · 📞 {client.get('phone') or '—'} · долг **{int(debt_now):,} сом**".replace(",", " "))

    # ----- форма оплаты: сразу под выбором клиента -----
    client_sales = [s for s in sales if s.get("client_id") == cid]
    sale_labels = {}
    for s in client_sales:
        sale_pays = [p for p in payments if p.get("sale_id") == s.get("id")]
        paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_pays)
        debt = float(s.get("credit_balance", 0) or 0) - paid
        if debt <= 0.5:
            continue
        sale_labels[s.get("id")] = (f"{str(s.get('name', ''))[:55]} | долг {int(debt):,}", s)
    if not sale_labels:
        if not receipt:
            st.success("По этому клиенту долга уже нет.")
        return

    if len(sale_labels) == 1:
        # один договор — выбирать не нужно
        sale_id = next(iter(sale_labels))
        st.caption(f"Договор: {sale_labels[sale_id][0]}")
    else:
        sale_options = [None] + list(sale_labels.keys())
        def sale_format(i):
            if i is None:
                return "— Выберите договор —"
            return sale_labels[i][0]
        if st.session_state.get("credit_sale_pick") not in sale_options:
            st.session_state["credit_sale_pick"] = None
        sale_id = st.selectbox("Договор", sale_options, format_func=sale_format, key="credit_sale_pick")
        if sale_id is None:
            st.info("Выберите договор.")
            return
    sale = sale_labels[sale_id][1]
    sale_pays = [p for p in payments if p.get("sale_id") == sale.get("id")]
    unpaid = sorted(
        [p for p in sale_pays if float(p.get("amount_expected", 0) or 0) - float(p.get("amount_paid", 0) or 0) > 0.5],
        key=lambda p: parse_due(p.get("due_date")) or today,
    )
    pay_labels = {}
    for p in unpaid:
        due = parse_due(p.get("due_date"))
        left_amt = float(p.get("amount_expected", 0) or 0) - float(p.get("amount_paid", 0) or 0)
        due_txt = due.strftime("%d.%m.%Y") if due else "—"
        mark = "просрочка" if due and due < today else ("сегодня" if due == today else "")
        pay_labels[p["id"]] = (f"{due_txt} | осталось {int(left_amt):,} сом {mark}".strip(), p)
    if not pay_labels:
        st.info("Неоплаченных месяцев нет.")
        return

    # по умолчанию — ближайший неоплаченный месяц; ручной выбор по желанию
    pay_options = list(pay_labels.keys())
    pick_key = f"credit_pay_pick_{sale_id}"
    if st.session_state.get(pick_key) not in pay_options:
        st.session_state[pick_key] = pay_options[0]
    pay_id = st.session_state[pick_key]
    st.caption(f"Зачислится на: {pay_labels[pay_id][0]}")
    with st.expander("Выбрать месяц вручную"):
        st.selectbox("Куда зачислить", pay_options, format_func=lambda i: pay_labels[i][0], key=pick_key)
    target = pay_labels[pay_id][1]
    left_amt = float(target.get("amount_expected", 0) or 0) - float(target.get("amount_paid", 0) or 0)
    amount = st.number_input("Сумма оплаты, сом", min_value=0.0, value=float(int(left_amt)), step=100.0,
                             key=f"accept_amount_{target['id']}")
    if st.button("💳 Принять оплату", type="primary", width="stretch"):
        accept_payment(unpaid, amount, client.get("fio", "клиент"), target["id"], cid)
    st.caption("Если сумма больше этого месяца, остаток сам уйдёт на следующие платежи.")

    # ----- подробности ниже -----
    st.button("📱 Выписка для клиента (скриншот)", width="stretch",
              on_click=open_client_statement, args=(cid,), key="open_statement_btn")
    from obligation import obligation_button
    obligation_button(sale.get("id"), key="obl_clients")
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
        st.dataframe(pd.DataFrame(show_rows), width="stretch", hide_index=True)

    if user_role == "Администратор":
        with st.expander("🛠️ Правка графика (админ)"):
            new_day = st.number_input("Поставить оставшиеся платежи на число", min_value=1, max_value=28, value=10, key="shift_day")
            if st.button("Сдвинуть оставшиеся на это число"):
                shift_remaining(unpaid, int(new_day))

            edit_p = target
            if float(edit_p.get("amount_paid", 0) or 0) > 0.5:
                from installment_logic import LOCKED_ROW_MESSAGE
                st.info(LOCKED_ROW_MESSAGE)
            else:
                due = parse_due(edit_p.get("due_date")) or today
                new_due = st.date_input("Дата выбранного платежа", value=due, key=f"one_due_{edit_p['id']}")
                new_expected = st.number_input("Сумма выбранного платежа", min_value=0.0,
                                               value=float(edit_p.get("amount_expected", 0) or 0), step=50.0,
                                               key=f"one_amt_{edit_p['id']}")
                if st.button("Сохранить дату и сумму"):
                    save_single_payment(sale, sale_pays, edit_p["id"], new_due, new_expected)

            open_count = len([p for p in sale_pays if float(p.get("amount_paid", 0) or 0) <= 0.5])
            months = st.number_input("Разложить неоплаченный остаток на месяцев", min_value=1, max_value=36,
                                     value=max(open_count, 1), key="rebuild_months")
            if st.button(
                "Пересоздать неоплаченные платежи с текущего месяца",
                help="Оплаченные и частично оплаченные платежи не меняются. Неоплаченные раскладываются заново "
                     "поровну, чтобы весь график = сумме рассрочки по договору. Изменения пишутся в журнал.",
            ):
                rebuild_schedule(sale, sale_pays, int(months))

        from installment_admin import show_transfer
        show_transfer(sale, client, clients, key_prefix="cl")

    with st.expander(f"📋 Все должники ({len(rows)})"):
        st.dataframe(pd.DataFrame([{
            "": r["status"], "ФИО": r["fio"], "Телефон": r["phone"], "Долг": int(r["debt"]),
            "Ближайший платёж": r["next_due"].strftime("%d.%m.%Y") if r["next_due"] else "—",
        } for r in rows]), width="stretch", hide_index=True)


def close_receipt():
    st.session_state.pop(RECEIPT_KEY, None)


def show_receipt(receipt, client, cid, sales, payments, today):
    """Квитанция после оплаты: держится, пока не закроют или не выберут другого клиента."""
    with st.container(border=True):
        if receipt.get("ok"):
            st.success(f"Оплата {int(receipt['applied']):,} сом принята · {receipt['client_name']} · {receipt['time']}".replace(",", " "), icon="✅")
            if receipt.get("extra", 0) > 0.5:
                st.warning(f"Лишние {int(receipt['extra']):,} сом некуда зачислить — долг по договору закрыт. Верните их клиенту.".replace(",", " "))
            try:
                from statement import build_statement, render_card, show_image_buttons
                data = build_statement(cid, sales, payments, today)
                render_card(client, data, today, show_closed=False, page_chrome=False)
                show_image_buttons(client, data, today, False, cid, key_prefix="receipt")
            except Exception as e:
                st.caption(f"Выписку показать не получилось: {e}")
        else:
            st.error(f"Оплата НЕ сохранена: {receipt.get('error')}", icon="❌")
        st.button("✖️ Закрыть", on_click=close_receipt, key="close_receipt", width="stretch")


def open_client_statement(client_id):
    try:
        from statement import open_statement
        open_statement(client_id)
    except Exception:
        pass


def accept_payment(unpaid, amount, client_name, start_id, client_id=None):
    """Записывает оплату. Если касса не записалась — строки графика возвращаются как были."""
    from payment_logic import plan_payment
    now = datetime.now()
    base = {"client_id": client_id, "client_name": client_name, "time": now.strftime("%d.%m.%Y %H:%M")}
    try:
        plan = plan_payment(unpaid, amount, start_id)
    except ValueError as e:
        st.error(str(e))
        return
    done = []
    try:
        for ch in plan["changes"]:
            supabase.table("credit_payments").update(ch["new"]).eq("id", ch["id"]).execute()
            done.append(ch)
        supabase.table("cash_operations").insert({
            "date": now.strftime("%d.%m.%Y %H:%M"),
            "amount": plan["applied"],
            "comment": f"Погашение рассрочки от {client_name}",
        }).execute()
    except Exception as e:
        rollback_failed = []
        for ch in reversed(done):
            try:
                supabase.table("credit_payments").update(ch["old"]).eq("id", ch["id"]).execute()
            except Exception:
                rollback_failed.append(ch["id"])
        msg = f"{e}."
        if rollback_failed:
            msg += f" ВНИМАНИЕ: не удалось вернуть платежи {rollback_failed} — проверьте график в «🛠️ Правка рассрочек»."
        else:
            msg += " Ничего не записано, попробуйте ещё раз."
        st.session_state[RECEIPT_KEY] = {**base, "ok": False, "error": msg}
        st.rerun()
    st.session_state[RECEIPT_KEY] = {**base, "ok": True, "applied": plan["applied"], "extra": plan["extra"]}
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


def save_single_payment(sale, sale_pays, row_id, new_due, new_amount):
    """Правка одного неоплаченного платежа: проверка админа и журнал — через installment_admin."""
    from installment_logic import plan_single_row_edit
    from installment_admin import NotAdmin, apply_schedule_plan
    try:
        plan = plan_single_row_edit(sale, sale_pays, row_id, new_due, new_amount)
    except ValueError as e:
        st.error(str(e))
        return
    if plan["errors"]:
        st.error("; ".join(plan["errors"]))
        return
    if not plan["changed"]:
        st.info("Ничего не изменилось")
        return
    try:
        apply_schedule_plan(sale, plan, "Правка одного платежа (Клиенты)")
    except NotAdmin as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Ошибка: {e}. Обновите страницу и проверьте график.")
        return
    st.success("Платёж обновлён")
    st.rerun()


def rebuild_schedule(sale, sale_pays, months):
    """Пересобирает только неоплаченные строки; оплаченные и частичные не трогает."""
    from installment_logic import plan_rebuild_unpaid
    from installment_admin import NotAdmin, apply_schedule_plan
    try:
        plan = plan_rebuild_unpaid(sale, sale_pays, months, datetime.now().date())
    except ValueError as e:
        st.error(str(e))
        return
    if plan["errors"]:
        st.error("; ".join(plan["errors"]))
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
            from obligation import doc_fields_input
            extra = doc_fields_input(prefix="reg")
            if st.form_submit_button("Зарегистрировать"):
                if fio:
                    supabase.table("clients").insert({
                        "fio": fio,
                        "phone": phone or None,
                        "address": address or None,
                        "passport": passport or None,
                        **extra,
                    }).execute()
                    st.success("Клиент добавлен")
                    st.rerun()
    with col2:
        st.subheader("Изменить клиента")
        if clients:
            from client_logic import client_label
            opts = {c["id"]: c for c in clients}
            pick = st.selectbox("Клиент", list(opts.keys()), index=None, format_func=lambda i: client_label(opts[i]),
                                placeholder="Начните вводить ФИО...", key="client_edit_pick")
            if pick is None:
                st.info("Выберите клиента для изменения.")
            else:
                person = opts[pick]
                with st.form("client_edit_form"):
                    new_fio = st.text_input("ФИО", value=str(person.get("fio") or ""))
                    new_phone = st.text_input("Телефон", value=str(person.get("phone") or ""))
                    new_address = st.text_input("Адрес", value=str(person.get("address") or ""))
                    new_passport = st.text_area("Паспорт", value=str(person.get("passport") or ""))
                    from obligation import doc_fields_input
                    extra = doc_fields_input(person, prefix=f"edit_{person.get('id')}")
                    if st.form_submit_button("Сохранить"):
                        supabase.table("clients").update({
                            "fio": new_fio.strip(),
                            "phone": new_phone.strip() or None,
                            "address": new_address.strip() or None,
                            "passport": new_passport.strip() or None,
                            **extra,
                        }).eq("id", person["id"]).execute()
                        st.success("Сохранено")
                        st.rerun()
    if clients:
        df = pd.DataFrame(clients).drop(columns=["created_at"], errors="ignore")
        st.dataframe(df, width="stretch", hide_index=True)


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
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
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
