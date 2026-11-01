# Магазин «Сулайман-Тоо» — Логика сводки за период (без Streamlit и без базы)
# Версия: 1.0

from installment_logic import parse_day
from cash_logic import get_category_from_comment, CAT_NEEDS, CAT_SUPPLIER, CAT_ANNUL, CAT_DEPOSIT, CAT_NONE

REPAY_PREFIX = "Погашение рассрочки от "
DOWN_PREFIX = "Перв. взнос по рассрочке"


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _in(d, start, end):
    return d is not None and start <= d <= end


def repayment_client(comment):
    c = str(comment or "").strip()
    return c[len(REPAY_PREFIX):].strip() if c.startswith(REPAY_PREFIX) else None


def nearest_due(client_rows, pay_day):
    """Ближайшая к дню оплаты дата по графику клиента (только строки, где есть оплата, иначе все)."""
    rows = [r for r in client_rows if _num(r.get("amount_paid")) > 0.5] or list(client_rows)
    dues = [parse_day(r.get("due_date")) for r in rows]
    dues = [d for d in dues if d]
    if not dues or not pay_day:
        return None
    return min(dues, key=lambda d: (abs((d - pay_day).days), d))


def timing_label(days):
    if days is None:
        return "—"
    if days < 0:
        return f"Раньше на {-days} дн."
    if days > 0:
        return f"Позже на {days} дн."
    return "В срок"


def period_summary(start, end, sales, ops, products, payments, clients):
    """Сводка за период [start, end] (даты включительно)."""
    clients_by_id = {c.get("id"): c for c in clients}
    client_ids_by_name = {}
    for c in clients:
        client_ids_by_name.setdefault(str(c.get("fio") or "").strip(), []).append(c.get("id"))

    issued = [s for s in sales if s.get("payment") == "Рассрочка" and _in(parse_day(s.get("date")), start, end)]
    issued_rows = []
    for s in issued:
        cl = clients_by_id.get(s.get("client_id"), {})
        issued_rows.append({
            "date": parse_day(s.get("date")), "client": cl.get("fio", "—"), "contract": s.get("name", ""),
            "goods": _num(s.get("total_sale")), "down": _num(s.get("down_payment")),
            "credit": _num(s.get("credit_balance")),
        })

    cash_sales = sum(_num(s.get("total_sale")) for s in sales
                     if s.get("payment") == "Наличные" and _in(parse_day(s.get("date")), start, end))

    rows_by_client = {}
    for p in payments:
        rows_by_client.setdefault(p.get("client_id"), []).append(p)

    repay_rows = []
    annul_sum = needs = supplier = other_out = deposits = down_sum = 0.0
    annul_count = 0
    for op in ops:
        d = parse_day(op.get("date"))
        if not _in(d, start, end):
            continue
        amt = _num(op.get("amount"))
        comment = op.get("comment", "")
        cat = get_category_from_comment(comment)
        name = repayment_client(comment)
        if name is not None and amt > 0:
            rows = []
            for cid in client_ids_by_name.get(name, []):
                rows += rows_by_client.get(cid, [])
            due = nearest_due(rows, d)
            days = (d - due).days if due else None
            repay_rows.append({"date": d, "time": str(op.get("date") or "")[11:16], "client": name,
                               "amount": amt, "due": due, "days": days, "timing": timing_label(days)})
        elif cat == CAT_ANNUL:
            annul_sum += abs(amt)
            annul_count += 1
        elif str(comment).strip().startswith(DOWN_PREFIX) and amt > 0:
            down_sum += amt
        elif cat == CAT_DEPOSIT and amt > 0:
            deposits += amt
        elif amt < 0:
            if cat == CAT_NEEDS:
                needs += -amt
            elif cat == CAT_SUPPLIER:
                supplier += -amt
            else:
                other_out += -amt

    received_qty = 0
    received_cost = 0.0
    for p in products:
        if _in(parse_day(p.get("date")), start, end):
            q = _num(p.get("qty"))
            received_qty += int(q)
            received_cost += q * _num(p.get("cost"))

    repay_sum = sum(r["amount"] for r in repay_rows)
    repay_rows.sort(key=lambda r: (r["date"], r["time"]))
    return {
        "issued_count": len(issued), "issued_goods": sum(r["goods"] for r in issued_rows),
        "issued_credit": sum(r["credit"] for r in issued_rows), "issued_rows": issued_rows,
        "down_sum": down_sum, "cash_sales": cash_sales,
        "repay_count": len(repay_rows), "repay_sum": repay_sum,
        "annul_count": annul_count, "annul_sum": annul_sum, "repay_net": repay_sum - annul_sum,
        "repay_rows": repay_rows,
        "early": sum(1 for r in repay_rows if r["days"] is not None and r["days"] < 0),
        "ontime": sum(1 for r in repay_rows if r["days"] == 0),
        "late": sum(1 for r in repay_rows if r["days"] is not None and r["days"] > 0),
        "received_qty": received_qty, "received_cost": received_cost,
        "supplier": supplier, "needs": needs, "other_out": other_out, "deposits": deposits,
    }
