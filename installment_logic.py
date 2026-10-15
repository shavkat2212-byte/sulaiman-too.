# Магазин «Сулайман-Тоо» — Логика правки рассрочек (без Streamlit и без базы)
# Версия: 1.0
# Здесь только расчёты: что можно менять, какие записи обновить/добавить/удалить,
# что записать в кассу при аннулировании. Модуль installment_admin.py выполняет это в базе.

import calendar
from datetime import date, datetime

STATUS_PAID = "Оплачен"
STATUS_PARTIAL = "Частично"
STATUS_UNPAID = "Не оплачен"
ANNUL_PREFIX = "[АННУЛИРОВАНИЕ]"
TOLERANCE = 0.5      # как в остальном приложении: меньше 0.5 сом считаем нулём
MIN_REASON_LEN = 3


def num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def clean_amount(value):
    """Целые суммы пишем как int (как sales.py), дробные — с 2 знаками."""
    value = round(float(value), 2)
    return int(value) if value == int(value) else value


def parse_day(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def day_str(value):
    d = parse_day(value)
    return d.strftime("%Y-%m-%d") if d else None


def row_expected(row):
    return num(row.get("amount_expected"))


def row_paid(row):
    return num(row.get("amount_paid"))


def is_locked(row):
    """Строка с любой принятой оплатой — оплачена или частично. Её не правим, только аннулируем."""
    return row_paid(row) > TOLERANCE


def status_for(expected, paid):
    if paid <= TOLERANCE:
        return STATUS_UNPAID
    if paid + TOLERANCE >= expected:
        return STATUS_PAID
    return STATUS_PARTIAL


def sort_rows(rows):
    return sorted(rows, key=lambda r: (parse_day(r.get("due_date")) or date.max, str(r.get("id"))))


def schedule_totals(credit_balance, rows):
    """Сверка: сумма графика должна равняться сумме рассрочки (credit_balance) по договору."""
    expected = sum(row_expected(r) for r in rows)
    paid = sum(row_paid(r) for r in rows)
    balance = num(credit_balance)
    diff = expected - balance
    return {
        "credit_balance": balance,
        "schedule_total": expected,
        "paid": paid,
        "remaining": balance - paid,
        "schedule_left": expected - paid,
        "diff": diff,
        "ok": abs(diff) <= 1,
    }


def add_month(d, months, day=None):
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = day or d.day
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def generate_open_rows(amount, monthly, first_due):
    """Раскладывает сумму на месяцы по monthly; последний месяц — остаток."""
    amount = round(num(amount), 2)
    monthly = round(num(monthly), 2)
    first_due = parse_day(first_due)
    if amount <= TOLERANCE:
        return []
    if monthly <= 0:
        raise ValueError("Ежемесячный платёж должен быть больше 0")
    if not first_due:
        raise ValueError("Укажите дату первого платежа")
    rows, left, i = [], amount, 0
    while left > TOLERANCE:
        if i >= 120:
            raise ValueError("Слишком много месяцев (больше 120). Увеличьте ежемесячный платёж.")
        pay = monthly if left - monthly > TOLERANCE else left
        rows.append({"id": None, "due": add_month(first_due, i, first_due.day), "amount": clean_amount(pay)})
        left = round(left - pay, 2)
        i += 1
    return rows


def reuse_ids(new_rows, old_draft):
    """Новые строки забирают id старых неоплаченных строк по порядку: меньше удалений в журнале."""
    ids = [r.get("id") for r in old_draft if r.get("id")]
    out = []
    for i, r in enumerate(new_rows):
        r = dict(r)
        r["id"] = ids[i] if i < len(ids) else None
        out.append(r)
    return out


def plan_schedule_save(sale, old_rows, draft, new_credit_balance=None):
    """
    sale       — договор (sales), old_rows — его строки credit_payments из базы.
    draft      — неоплаченные строки после правки: [{"id": id|None, "due": date, "amount": число}].
    Возвращает план: updates / inserts / deletes / contract_update / check / errors.
    Оплаченные и частично оплаченные строки план не трогает никогда.
    """
    errors = []
    by_id = {str(r.get("id")): r for r in old_rows}
    locked = [r for r in old_rows if is_locked(r)]
    open_old = {str(r.get("id")): r for r in old_rows if not is_locked(r)}

    updates, inserts, keep_ids = [], [], set()
    for n, item in enumerate(draft, start=1):
        rid = item.get("id")
        rid = None if rid in (None, "") or (isinstance(rid, float) and rid != rid) else str(rid)
        if isinstance(rid, str) and rid.endswith(".0") and rid[:-2].isdigit() and rid not in by_id:
            rid = rid[:-2]
        due = parse_day(item.get("due"))
        amount = num(item.get("amount"))
        if not due:
            errors.append(f"Строка {n}: не указана дата")
            continue
        if amount <= 0:
            errors.append(f"Строка {n}: сумма должна быть больше 0")
            continue
        if rid is not None:
            if rid not in by_id:
                errors.append(f"Строка {n}: платёж #{rid} не относится к этому договору")
                continue
            if rid not in open_old:
                errors.append(f"Строка {n}: платёж #{rid} уже оплачен — его нельзя менять, только аннулировать")
                continue
            if rid in keep_ids:
                errors.append(f"Строка {n}: платёж #{rid} указан дважды")
                continue
            keep_ids.add(rid)
            old = open_old[rid]
            new = {"due_date": due.strftime("%Y-%m-%d"), "amount_expected": clean_amount(amount)}
            if day_str(old.get("due_date")) != new["due_date"] or abs(row_expected(old) - amount) > 0.004:
                new["status"] = status_for(amount, row_paid(old))
                updates.append({
                    "id": old.get("id"),
                    "old": {"due_date": old.get("due_date"), "amount_expected": old.get("amount_expected"),
                            "status": old.get("status")},
                    "new": new,
                })
        else:
            inserts.append({
                "sale_id": sale.get("id"),
                "client_id": sale.get("client_id"),
                "due_date": due.strftime("%Y-%m-%d"),
                "amount_expected": clean_amount(amount),
                "amount_paid": 0,
                "status": STATUS_UNPAID,
            })

    deletes = [r for rid, r in open_old.items() if rid not in keep_ids]

    old_balance = num(sale.get("credit_balance"))
    contract_update = None
    balance = old_balance
    if new_credit_balance is not None and abs(num(new_credit_balance) - old_balance) > 0.004:
        if num(new_credit_balance) < 0:
            errors.append("Сумма рассрочки не может быть меньше 0")
        else:
            balance = num(new_credit_balance)
            contract_update = {
                "old": {"credit_balance": sale.get("credit_balance")},
                "new": {"credit_balance": clean_amount(balance)},
            }
    paid_total = sum(row_paid(r) for r in old_rows)
    if balance + TOLERANCE < paid_total:
        errors.append(f"Сумма рассрочки {balance:,.0f} меньше уже оплаченного {paid_total:,.0f}")

    result_rows = list(locked)
    for rid in keep_ids:
        r = dict(open_old[rid])
        upd = next((u for u in updates if str(u["id"]) == rid), None)
        if upd:
            r.update(upd["new"])
        result_rows.append(r)
    result_rows += inserts
    check = schedule_totals(balance, result_rows)

    return {
        "updates": updates,
        "inserts": inserts,
        "deletes": deletes,
        "contract_update": contract_update,
        "check": check,
        "errors": errors,
        "changed": bool(updates or inserts or deletes or contract_update),
    }


def plan_annulment(row, amount, reason, client_name, now=None):
    """
    Аннулирование принятой оплаты по строке графика.
    Возвращает новое состояние строки и обратную (минусовую) запись в кассу.
    """
    now = now or datetime.now()
    reason = str(reason or "").strip()
    paid = row_paid(row)
    amount = round(num(amount), 2)
    if not is_locked(row):
        raise ValueError("По этому платежу оплаты нет — аннулировать нечего")
    if len(reason) < MIN_REASON_LEN:
        raise ValueError("Укажите причину аннулирования")
    if amount <= 0:
        raise ValueError("Сумма аннулирования должна быть больше 0")
    if amount > paid + 0.004:
        raise ValueError(f"Нельзя аннулировать больше, чем оплачено ({paid:,.0f} сом)")
    new_paid = round(paid - amount, 2)
    if new_paid <= TOLERANCE:
        new_paid = 0
    new_paid = clean_amount(new_paid)
    expected = row_expected(row)
    due = parse_day(row.get("due_date"))
    due_txt = due.strftime("%d.%m.%Y") if due else str(row.get("due_date") or "—")
    return {
        "row_id": row.get("id"),
        "old": {"amount_paid": row.get("amount_paid"), "status": row.get("status")},
        "new": {"amount_paid": new_paid, "status": status_for(expected, num(new_paid))},
        "cash_entry": {
            "date": now.strftime("%Y-%m-%d %H:%M"),
            "amount": -clean_amount(amount),
            "comment": f"{ANNUL_PREFIX} Отмена погашения рассрочки от {client_name}, платёж {due_txt}: {reason}",
        },
        "amount": clean_amount(amount),
        "reason": reason,
    }


def plan_rebuild_unpaid(sale, old_rows, months, start, pay_day=None):
    """
    «Пересоздать график»: оплаченные и частично оплаченные строки не трогаем.
    Неоплаченные раскладываем заново на months месяцев с месяца после start так,
    чтобы сумма всего графика = credit_balance (оплаченные строки + новые неоплаченные).
    """
    months = int(months or 0)
    start = parse_day(start)
    if months <= 0:
        raise ValueError("Количество месяцев должно быть больше 0")
    if not start:
        raise ValueError("Не указана дата начала")
    locked = [r for r in old_rows if is_locked(r)]
    open_needed = round(num(sale.get("credit_balance")) - sum(row_expected(r) for r in locked), 2)
    if open_needed <= TOLERANCE:
        raise ValueError("Нечего пересобирать: неоплаченного остатка по графику нет")
    monthly = open_needed / months
    monthly = round(monthly) if open_needed == int(open_needed) else round(monthly, 2)
    day = min(int(pay_day or start.day), 28)
    draft, left = [], open_needed
    for i in range(1, months + 1):
        pay = round(left, 2) if i == months else monthly
        left = round(left - pay, 2)
        draft.append({"id": None, "due": add_month(start.replace(day=1), i, day), "amount": clean_amount(pay)})
    old_draft = [{"id": str(r.get("id"))} for r in sort_rows(old_rows) if not is_locked(r)]
    return plan_schedule_save(sale, old_rows, reuse_ids(draft, old_draft))


LOCKED_ROW_MESSAGE = ("Этот платёж уже оплачен (полностью или частично) — менять его нельзя. "
                      "Откройте «🛠️ Правка рассрочек», сначала аннулируйте оплату, затем исправьте платёж "
                      "и примите оплату заново.")


def plan_single_row_edit(sale, old_rows, row_id, new_due, new_amount):
    """Правка даты и суммы одного платежа (Клиенты → «Сохранить дату и сумму»). Оплаченные — запрещено."""
    target = next((r for r in old_rows if str(r.get("id")) == str(row_id)), None)
    if target is None:
        raise ValueError("Платёж не найден в этом договоре")
    if is_locked(target):
        raise ValueError(LOCKED_ROW_MESSAGE)
    draft = []
    for r in sort_rows(old_rows):
        if is_locked(r):
            continue
        if str(r.get("id")) == str(row_id):
            draft.append({"id": str(r.get("id")), "due": new_due, "amount": new_amount})
        else:
            draft.append({"id": str(r.get("id")), "due": parse_day(r.get("due_date")), "amount": row_expected(r)})
    return plan_schedule_save(sale, old_rows, draft)


# ---------- изменение срока (реструктуризация) ----------
MARKUP_PER_MONTH = 3.0  # % за месяц, как при оформлении продажи (sales.py: наценка = срок × 3%)


def net_debt(sale):
    """Чистый долг без наценки: цена товара минус первый взнос."""
    return max(round(num(sale.get("total_sale")) - num(sale.get("down_payment")), 2), 0.0)


def suggest_total(sale, months, percent_per_month=MARKUP_PER_MONTH):
    """Сумма рассрочки по стандартной наценке для нового срока (всего месяцев)."""
    return float(round(net_debt(sale) * (1 + percent_per_month * int(months) / 100)))


def plan_restructure(sale, old_rows, total_months, first_due, new_total=None):
    """
    Новый срок договора: total_months — весь срок (вместе с уже оплаченными месяцами).
    Оплаченные/частично оплаченные строки не меняются. Остаток (new_total − их суммы)
    делится поровну на оставшиеся месяцы, копеечный/сомовый остаток — в последний месяц.
    new_total=None — сумма рассрочки не меняется.
    """
    total_months = int(total_months or 0)
    first_due = parse_day(first_due)
    if not first_due:
        raise ValueError("Укажите дату первого неоплаченного платежа")
    locked = [r for r in old_rows if is_locked(r)]
    rest = total_months - len(locked)
    if rest < 1:
        raise ValueError(f"Срок должен быть больше уже оплаченных месяцев ({len(locked)})")
    balance = num(sale.get("credit_balance")) if new_total is None else num(new_total)
    open_needed = round(balance - sum(row_expected(r) for r in locked), 2)
    if open_needed <= TOLERANCE:
        raise ValueError("Нечего распределять: сумма рассрочки уже покрыта оплаченными платежами")
    whole = open_needed == int(open_needed)
    monthly = (open_needed // rest) if whole else round(open_needed / rest, 2)
    dates = month_schedule(first_due, rest)
    draft, left = [], open_needed
    for i in range(rest):
        pay = round(left, 2) if i == rest - 1 else monthly
        left = round(left - pay, 2)
        draft.append({"id": None, "due": dates[i], "amount": clean_amount(pay)})
    old_draft = [{"id": str(r.get("id"))} for r in sort_rows(old_rows) if not is_locked(r)]
    plan = plan_schedule_save(sale, old_rows, reuse_ids(draft, old_draft),
                              None if new_total is None else balance)
    plan["preview"] = draft
    plan["restructure"] = {
        "old": {"months": len(old_rows), "credit_balance": num(sale.get("credit_balance"))},
        "new": {"months": total_months, "credit_balance": balance, "open_months": rest},
    }
    return plan


# ---------- аннулирование всего договора ----------
STATUS_ANNULLED = "Аннулирован"
SALE_ANNULLED_PAYMENT = "Аннулирован"   # sales.payment: договор пропадает из долгов и отчётов
SALE_ANNULLED_PREFIX = "[АННУЛИРОВАН] "


def month_schedule(first_due, count):
    """Даты платежей: первая выбрана в календаре, дальше каждый месяц тем же числом.
    Если в месяце нет такого числа (31, 30, 29 февраля) — последний день месяца."""
    first_due = parse_day(first_due)
    return [add_month(first_due, i, first_due.day) for i in range(int(count))]


def parse_goods(sale_name):
    """«Договор рассрочки №… [Холодильник lg (1 шт.), Чайник (2 шт.)] — ФИО» → [(название, кол-во)]."""
    import re
    text = str(sale_name or "")
    if "[" not in text or "]" not in text:
        return []
    inner = text[text.index("[") + 1:text.rindex("]")]
    return [(m.group(1).strip(), int(m.group(2))) for m in re.finditer(r"\s*(.+?) \((\d+) шт\.\),?", inner)]


def plan_contract_annulment(sale, rows, reason, client_name, now=None):
    """Возвращает план полного аннулирования договора (без записи в базу)."""
    now = now or datetime.now()
    reason = str(reason or "").strip()
    if len(reason) < MIN_REASON_LEN:
        raise ValueError("Укажите причину аннулирования договора")
    if str(sale.get("payment") or "") == SALE_ANNULLED_PAYMENT:
        raise ValueError("Договор уже аннулирован")
    stamp = now.strftime("%Y-%m-%d %H:%M")
    paid = round(sum(row_paid(r) for r in rows), 2)
    down = round(num(sale.get("down_payment")), 2)
    cash = []
    if paid > TOLERANCE:
        cash.append({"date": stamp, "amount": -clean_amount(paid),
                     "comment": f"{ANNUL_PREFIX} Возврат погашений по аннулированному договору {sale.get('id')} ({client_name}): {reason}"})
    if down > TOLERANCE:
        cash.append({"date": stamp, "amount": -clean_amount(down),
                     "comment": f"{ANNUL_PREFIX} Возврат первого взноса по аннулированному договору {sale.get('id')} ({client_name}): {reason}"})
    row_updates = [{"id": r.get("id"),
                    "old": {"amount_paid": r.get("amount_paid"), "status": r.get("status")},
                    "new": {"amount_paid": 0, "status": STATUS_ANNULLED}} for r in rows]
    name = str(sale.get("name") or "")
    sale_new = {"payment": SALE_ANNULLED_PAYMENT,
                "name": name if name.startswith(SALE_ANNULLED_PREFIX) else SALE_ANNULLED_PREFIX + name}
    return {
        "cash_entries": cash,
        "refund_total": clean_amount(paid + down),
        "paid": clean_amount(paid), "down": clean_amount(down),
        "row_updates": row_updates,
        "sale_update": {"old": {"payment": sale.get("payment"), "name": sale.get("name"),
                                "credit_balance": sale.get("credit_balance")}, "new": sale_new},
        "goods": parse_goods(name),
        "reason": reason,
    }
