# Права на складе: кассир может менять только название товара, остальное — Администратор.
ADMIN_ROLE = "Администратор"
CASHIER_EDITABLE_FIELDS = ("name",)


def is_admin(role) -> bool:
    return role == ADMIN_ROLE


def allowed_product_update(role, data: dict) -> dict:
    """Возвращает только те поля, которые эта роль имеет право менять."""
    if is_admin(role):
        return dict(data)
    return {k: v for k, v in data.items() if k in CASHIER_EDITABLE_FIELDS}


def can_delete_product(role) -> bool:
    return is_admin(role)


def can_add_products(role) -> bool:
    return is_admin(role)


def _num(v):
    try:
        if v is None or (isinstance(v, float) and v != v):
            return None
        s = str(v).replace(" ", "").replace(",", ".").strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def parse_stock_grid(rows):
    """Строки таблицы «как в Excel» → (товары, ошибки). Пустые строки пропускаются.
    Одинаковые названия в одной таблице складываются по количеству (цены — из последней строки)."""
    items, errors = {}, []
    for i, r in enumerate(rows or [], start=1):
        name = str(r.get("Товар") or "").strip().lower()
        if name in ("nan", "none"):
            name = ""
        qty, cost, price = _num(r.get("Кол-во")), _num(r.get("Себес")), _num(r.get("Прод"))
        if not name and qty is None and cost is None and price is None:
            continue
        if not name:
            errors.append(f"Строка {i}: нет названия товара"); continue
        if qty is None or qty <= 0 or qty != int(qty):
            errors.append(f"Строка {i} ({name}): количество должно быть целым больше 0"); continue
        cost = cost or 0.0
        price = price or 0.0
        if cost < 0 or price < 0:
            errors.append(f"Строка {i} ({name}): цены не могут быть отрицательными"); continue
        if name in items:
            items[name]["qty"] += int(qty)
            items[name].update(cost=cost, price=price)
        else:
            items[name] = {"name": name, "qty": int(qty), "cost": cost, "price": price}
    return list(items.values()), errors


def grid_total(items) -> float:
    return round(sum(i["qty"] * i["cost"] for i in items), 2)
