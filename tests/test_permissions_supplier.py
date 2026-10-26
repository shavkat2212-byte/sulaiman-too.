# Права кассира на складе и логика долга с поставщиком: python -m pytest tests/
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_logic import allowed_product_update, can_delete_product, can_add_products  # noqa: E402
from supplier_logic import (  # noqa: E402
    balance, pending_balance, can_create, can_accept, can_delete_entry, allowed_types,
    side_of_role, validate_amount, hash_token, new_token, SHOP, SUPPLIER,
)

FULL = {"name": "чайник", "qty": 5, "cost": 100, "price": 150, "date": "2026-10-26"}


def test_cashier_only_rename():
    assert allowed_product_update("Кассир", FULL) == {"name": "чайник"}
    assert allowed_product_update("Поставщик", FULL) == {"name": "чайник"}
    assert allowed_product_update("Администратор", FULL) == FULL


def test_delete_add_admin_only():
    assert can_delete_product("Администратор") and can_add_products("Администратор")
    assert not can_delete_product("Кассир") and not can_add_products("Кассир")


def test_create_rules():
    assert can_create("товар", SUPPLIER) and not can_create("товар", SHOP)
    assert can_create("оплата", SHOP) and not can_create("оплата", SUPPLIER)
    assert can_create("возврат", SHOP) and can_create("возврат", SUPPLIER)
    assert allowed_types(SUPPLIER) == ["товар", "возврат"]
    assert side_of_role("Кассир") == side_of_role("Администратор") == SHOP
    assert side_of_role("Поставщик") == SUPPLIER


def test_accept_rules():
    e = {"type": "товар", "amount": 100, "created_by_side": SUPPLIER, "accepted": False}
    assert can_accept(e, SHOP) and not can_accept(e, SUPPLIER)
    assert can_delete_entry(e, SUPPLIER) and not can_delete_entry(e, SHOP)
    e["accepted"] = True
    assert not can_accept(e, SHOP) and not can_delete_entry(e, SUPPLIER)
    assert can_accept({"created_by_role": "Поставщик", "accepted": False}, SHOP)


def test_balance():
    es = [
        {"type": "товар", "amount": 10000, "accepted": True},
        {"type": "оплата", "amount": 3000, "accepted": True},
        {"type": "возврат", "amount": 500.5, "accepted": True},
        {"type": "товар", "amount": 7000, "accepted": False},
        {"type": "оплата", "amount": 1000, "accepted": False},
    ]
    assert balance(es) == 6499.5
    assert pending_balance(es) == 6000
    assert balance([]) == 0


def test_amount_and_token():
    assert validate_amount(1) and not validate_amount(0) and not validate_amount("x")
    t = new_token()
    assert len(t) > 30 and hash_token(t) == hash_token(t) != t
