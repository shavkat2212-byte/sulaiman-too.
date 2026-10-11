# Магазин «Сулайман-Тоо» — Логика приёма оплаты по рассрочке (без Streamlit и без базы)
# Версия: 1.0


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def plan_payment(unpaid, amount, start_id):
    """
    Раскладывает оплату по неоплаченным строкам начиная со start_id (как раньше: излишек
    уходит на следующие месяцы). Возвращает {"changes", "applied", "extra"}.
    """
    amount = _num(amount)
    if amount <= 0:
        raise ValueError("Введите сумму больше 0")
    ordered = list(unpaid)
    start = next((i for i, p in enumerate(ordered) if p.get("id") == start_id), 0)
    left = amount
    applied = 0.0
    changes = []
    for p in ordered[start:]:
        if left <= 0:
            break
        expected = _num(p.get("amount_expected"))
        paid = _num(p.get("amount_paid"))
        room = expected - paid
        if room <= 0:
            continue
        take = min(room, left)
        new_paid = paid + take
        changes.append({
            "id": p.get("id"),
            "old": {"amount_paid": p.get("amount_paid"), "status": p.get("status")},
            "new": {"amount_paid": new_paid, "status": "Оплачен" if new_paid + 0.5 >= expected else "Частично"},
            "take": take,
        })
        left -= take
        applied += take
    if applied <= 0:
        raise ValueError("Некуда зачислить оплату: по договору нет неоплаченных платежей")
    return {"changes": changes, "applied": applied, "extra": max(amount - applied, 0.0)}
