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
