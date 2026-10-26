# Заказы поставщику, строки товаров и список склада «как в Excel»
import os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_logic import parse_stock_grid, grid_total  # noqa: E402
from supplier_logic import (  # noqa: E402
    SHOP, SUPPLIER, balance, parse_lines, lines_sum, next_status, can_confirm_order, can_accept_order,
    can_cancel_order, can_create_order, ledger_from_order,
)


def test_grid_parse_and_total():
    rows = [
        {"Товар": " Чайник ", "Кол-во": 2, "Себес": 1000, "Прод": 1500},
        {"Товар": "", "Кол-во": None, "Себес": None, "Прод": None},
        {"Товар": "чайник", "Кол-во": "3", "Себес": "1 100", "Прод": "1600"},
        {"Товар": "утюг", "Кол-во": 1, "Себес": None, "Прод": None},
    ]
    items, errors = parse_stock_grid(rows)
    assert errors == []
    assert items[0] == {"name": "чайник", "qty": 5, "cost": 1100.0, "price": 1600.0}
    assert items[1]["cost"] == 0.0
    assert grid_total(items) == 5500


def test_grid_errors():
    _, errors = parse_stock_grid([
        {"Товар": "", "Кол-во": 1}, {"Товар": "a", "Кол-во": 0}, {"Товар": "b", "Кол-во": 1.5},
        {"Товар": "c", "Кол-во": 1, "Себес": -1},
    ])
    assert len(errors) == 4


def test_lines():
    lines = parse_lines([{"Товар": "Кабель", "Кол-во": 10, "Цена": 50}, {"Товар": "", "Кол-во": 3},
                         {"Товар": "Лампа", "Кол-во": 2, "Примечание": "белая"}])
    assert [l["name"] for l in lines] == ["Кабель", "Лампа"]
    assert lines[0]["line_total"] == 500 and lines[1]["line_total"] is None and lines[1]["note"] == "белая"
    assert lines_sum(lines) == 500


def test_order_flow():
    o = {"id": 7, "status": "отправлен"}
    assert can_create_order(SHOP) and not can_create_order(SUPPLIER)
    assert not can_confirm_order(o, SHOP) and can_confirm_order(o, SUPPLIER)
    assert not can_accept_order(o, SHOP)
    with pytest.raises(ValueError):
        next_status(o, "accept", SHOP)
    assert next_status(o, "confirm", SUPPLIER) == "подтверждён"
    o.update(status="подтверждён", confirmed_amount=12000)
    assert can_accept_order(o, SHOP) and not can_accept_order(o, SUPPLIER)
    assert next_status(o, "accept", SHOP) == "принят"
    led = ledger_from_order(o)
    assert led["type"] == "товар" and led["amount"] == 12000 and led["accepted"] and led["order_id"] == 7
    assert balance([led, {"type": "оплата", "amount": 2000, "accepted": True}]) == 10000
    o["status"] = "принят"
    for side in (SHOP, SUPPLIER):
        assert not can_cancel_order(o, side) and not can_confirm_order(o, side)
    with pytest.raises(ValueError):
        next_status(o, "cancel", SHOP)


def test_order_cancel_and_zero_amount():
    o = {"status": "подтверждён", "confirmed_amount": 0}
    assert not can_accept_order(o, SHOP)
    assert can_cancel_order(o, SHOP) and can_cancel_order(o, SUPPLIER)
    assert next_status({"status": "отправлен"}, "cancel", SUPPLIER) == "отменён"
    with pytest.raises(ValueError):
        next_status(o, "bogus", SHOP)
