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
