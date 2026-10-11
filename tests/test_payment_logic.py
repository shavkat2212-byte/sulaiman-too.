import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from payment_logic import plan_payment  # noqa: E402

UNPAID = [
    {"id": 2, "amount_expected": 5600, "amount_paid": 2000, "status": "Частично"},
    {"id": 3, "amount_expected": 5600, "amount_paid": 0, "status": "Не оплачен"},
    {"id": 4, "amount_expected": 5600, "amount_paid": 0, "status": "Не оплачен"},
]


def test_exact_month():
    p = plan_payment(UNPAID, 3600, 2)
    assert p["applied"] == 3600 and p["extra"] == 0
    assert p["changes"] == [{"id": 2, "old": {"amount_paid": 2000, "status": "Частично"},
                             "new": {"amount_paid": 5600, "status": "Оплачен"}, "take": 3600}]


def test_overflow_to_next_and_partial():
    p = plan_payment(UNPAID, 6000, 2)
    assert [(c["id"], c["new"]["amount_paid"], c["new"]["status"]) for c in p["changes"]] == \
        [(2, 5600, "Оплачен"), (3, 2400, "Частично")]


def test_start_row_and_extra():
    p = plan_payment(UNPAID, 20000, 3)
    assert [c["id"] for c in p["changes"]] == [3, 4] and p["applied"] == 11200 and p["extra"] == 8800


def test_errors():
    with pytest.raises(ValueError):
        plan_payment(UNPAID, 0, 2)
    with pytest.raises(ValueError):
        plan_payment([], 100, 2)
