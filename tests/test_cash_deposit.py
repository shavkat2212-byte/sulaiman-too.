import pytest
from cash_logic import (CAT_DEPOSIT, get_category_from_comment, clean_comment, op_kind,
                        plan_cash_deposit, plan_cash_edit, check_cash_delete)


def test_deposit_row():
    r = plan_cash_deposit(5000, " возврат после аннулирования ", "2026-10-27 16:30")
    assert r == {"date": "2026-10-27 16:30", "amount": 5000.0, "comment": "[ВЗНОС] возврат после аннулирования"}
    assert get_category_from_comment(r["comment"]) == CAT_DEPOSIT
    assert clean_comment(r["comment"]) == "возврат после аннулирования"
    assert op_kind(r) == "income"


@pytest.mark.parametrize("amt,c", [(0, "текст"), (-5, "текст"), (100, ""), (100, " a ")])
def test_deposit_invalid(amt, c):
    with pytest.raises(ValueError):
        plan_cash_deposit(amt, c, "2026-10-27 16:30")


def test_deposit_edit_keeps_prefix_and_delete_allowed():
    op = {"amount": 5000, "comment": "[ВЗНОС] старый"}
    assert plan_cash_edit(op, 3000, "новый") == {"amount": 3000.0, "comment": "[ВЗНОС] новый"}
    assert plan_cash_edit(op, 3000, "[ВЗНОС] новый")["comment"] == "[ВЗНОС] новый"
    check_cash_delete(op)
