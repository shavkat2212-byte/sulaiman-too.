# Тесты правки кассовых операций: python -m pytest tests/
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cash_logic import check_cash_delete, clean_comment, get_category_from_comment, op_kind, plan_cash_edit  # noqa: E402

INCOME = {"id": 1, "amount": 5600, "comment": "Погашение рассрочки от Иванов Иван"}
DOWN = {"id": 2, "amount": 10000, "comment": "Перв. взнос по рассрочке №0108 от Иванов Иван"}
NEEDS = {"id": 3, "amount": -1500, "comment": "[НУЖДЫ] вода"}
SUPPLIER = {"id": 4, "amount": -20000, "comment": "[ПОСТАВЩИК] партия"}
OTHER = {"id": 5, "amount": -300, "comment": "прочее"}
ANNUL = {"id": 6, "amount": -5600, "comment": "[АННУЛИРОВАНИЕ] Отмена погашения рассрочки от Иванов Иван, платёж 01.09.2026: ошибка"}


def test_kinds():
    assert [op_kind(o) for o in (INCOME, DOWN, NEEDS, SUPPLIER, OTHER, ANNUL)] == \
        ["income", "income", "expense", "expense", "expense", "annul"]


def test_income_stays_positive():
    assert plan_cash_edit(INCOME, 6000, "Погашение рассрочки от Иванов Иван") == \
        {"amount": 6000.0, "comment": "Погашение рассрочки от Иванов Иван"}
    # даже если форма передала категорию расхода — приход не становится расходом
    assert plan_cash_edit(DOWN, -9000, "взнос", "Нужды магазина")["amount"] == 9000.0


def test_expense_stays_negative_with_prefix():
    assert plan_cash_edit(NEEDS, 2000, "вода и чай", "Нужды магазина") == {"amount": -2000.0, "comment": "[НУЖДЫ] вода и чай"}
    assert plan_cash_edit(NEEDS, 2000, "партия", "Оплата контрагенту") == {"amount": -2000.0, "comment": "[ПОСТАВЩИК] партия"}
    assert plan_cash_edit(SUPPLIER, 100, "x") == {"amount": -100.0, "comment": "[ПОСТАВЩИК] x"}
    assert plan_cash_edit(OTHER, 300, "прочее", "Без категории") == {"amount": -300.0, "comment": "прочее"}


def test_annulment_locked():
    with pytest.raises(ValueError):
        plan_cash_edit(ANNUL, 5600, clean_comment(ANNUL["comment"]))
    with pytest.raises(ValueError):
        check_cash_delete(ANNUL)
    check_cash_delete(INCOME)  # обычные операции удалять можно (как раньше)
    assert get_category_from_comment(ANNUL["comment"]) == "Аннулирование погашения"
    assert clean_comment(ANNUL["comment"]).startswith("Отмена погашения")


def test_zero_amount_rejected():
    with pytest.raises(ValueError):
        plan_cash_edit(INCOME, 0, "x")
