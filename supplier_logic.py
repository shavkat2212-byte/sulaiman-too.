# Учёт долга с поставщиком: только суммы, подтверждение другой стороной.
import hashlib
import secrets

SUPPLIER_ROLE = "Поставщик"
TYPE_GOODS, TYPE_PAYMENT, TYPE_RETURN = "товар", "оплата", "возврат"
TYPES = (TYPE_GOODS, TYPE_PAYMENT, TYPE_RETURN)
SHOP, SUPPLIER = "магазин", "поставщик"

# Кто может создавать запись каждого типа
CREATORS = {
    TYPE_GOODS: {SUPPLIER},
    TYPE_PAYMENT: {SHOP},
    TYPE_RETURN: {SHOP, SUPPLIER},
}


def side_of_role(role) -> str:
    return SUPPLIER if role == SUPPLIER_ROLE else SHOP


def can_create(op_type, side) -> bool:
    return side in CREATORS.get(op_type, set())


def allowed_types(side):
    return [t for t in TYPES if can_create(t, side)]


def can_accept(entry: dict, side) -> bool:
    """Подтверждает всегда другая сторона и только непринятую запись."""
    if entry.get("accepted"):
        return False
    creator = entry.get("created_by_side") or side_of_role(entry.get("created_by_role"))
    return creator != side


def can_delete_entry(entry: dict, side) -> bool:
    """Свою ещё не принятую запись можно отменить."""
    if entry.get("accepted"):
        return False
    creator = entry.get("created_by_side") or side_of_role(entry.get("created_by_role"))
    return creator == side


def signed_amount(entry: dict) -> float:
    amt = float(entry.get("amount") or 0)
    return amt if entry.get("type") == TYPE_GOODS else -amt


def balance(entries) -> float:
    """Долг магазина поставщику (>0 — магазин должен). Учитываются только принятые."""
    return round(sum(signed_amount(e) for e in entries if e.get("accepted")), 2)


def pending_balance(entries) -> float:
    return round(sum(signed_amount(e) for e in entries if not e.get("accepted")), 2)


def validate_amount(amount) -> bool:
    try:
        return float(amount) > 0
    except (TypeError, ValueError):
        return False


# --- «Запомнить меня»: в ссылке лежит случайный токен, в базе — только его хэш ---
def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(("sulaiman-session:" + token).encode("utf-8")).hexdigest()


# --- Строки товаров (для поставок, возвратов и заказов) ---
def parse_lines(rows):
    """Строки таблицы → список {name, qty, unit_price, line_total}. Пустые пропускаются."""
    out = []
    for r in rows or []:
        name = str(r.get("Товар") or "").strip()
        if name.lower() in ("", "nan", "none"):
            continue
        def num(v):
            try:
                if v is None or (isinstance(v, float) and v != v):
                    return None
                return float(str(v).replace(" ", "").replace(",", "."))
            except (TypeError, ValueError):
                return None
        qty = num(r.get("Кол-во"))
        price = num(r.get("Цена"))
        line = {"name": name, "qty": qty if qty and qty > 0 else None,
                "unit_price": price if price and price >= 0 else None,
                "note": (str(r.get("Примечание") or "").strip() or None) if r.get("Примечание") not in (None,) else None}
        if line["note"] in ("nan", "None"):
            line["note"] = None
        line["line_total"] = round(line["qty"] * line["unit_price"], 2) if line["qty"] and line["unit_price"] else None
        out.append(line)
    return out


def lines_sum(lines) -> float:
    return round(sum(l.get("line_total") or 0 for l in lines or []), 2)


# --- Заказы поставщику ---
ORDER_SENT, ORDER_CONFIRMED, ORDER_ACCEPTED, ORDER_CANCELLED = "отправлен", "подтверждён", "принят", "отменён"
ORDER_STATUSES = (ORDER_SENT, ORDER_CONFIRMED, ORDER_ACCEPTED, ORDER_CANCELLED)


def can_create_order(side) -> bool:
    return side == SHOP


def can_confirm_order(order: dict, side) -> bool:
    """Поставщик подтверждает отправленный заказ (или меняет сумму уже подтверждённого)."""
    return side == SUPPLIER and order.get("status") in (ORDER_SENT, ORDER_CONFIRMED)


def can_accept_order(order: dict, side) -> bool:
    """Магазин принимает подтверждённый заказ с суммой > 0."""
    return (side == SHOP and order.get("status") == ORDER_CONFIRMED
            and validate_amount(order.get("confirmed_amount")))


def can_cancel_order(order: dict, side) -> bool:
    return side in (SHOP, SUPPLIER) and order.get("status") in (ORDER_SENT, ORDER_CONFIRMED)


def next_status(order: dict, action: str, side) -> str:
    """action: confirm | accept | cancel. Бросает ValueError, если переход запрещён."""
    checks = {"confirm": (can_confirm_order, ORDER_CONFIRMED),
              "accept": (can_accept_order, ORDER_ACCEPTED),
              "cancel": (can_cancel_order, ORDER_CANCELLED)}
    if action not in checks:
        raise ValueError(f"Неизвестное действие: {action}")
    fn, new = checks[action]
    if not fn(order, side):
        raise ValueError(f"Нельзя: {action} при статусе «{order.get('status')}» для стороны «{side}»")
    return new


def ledger_from_order(order: dict) -> dict:
    """Запись долга, которая создаётся при приёмке заказа (сразу принята)."""
    return {"type": TYPE_GOODS, "amount": float(order["confirmed_amount"]), "accepted": True,
            "order_id": order.get("id"),
            "comment": f"Заказ №{order.get('id')}" + (f" · {order['comment']}" if order.get("comment") else "")}
