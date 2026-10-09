# Тесты логики правки рассрочек: python -m pytest tests/  (база не нужна)
import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from installment_logic import (  # noqa: E402
    ANNUL_PREFIX, generate_open_rows, plan_annulment, plan_schedule_save, schedule_totals, status_for,
)

SALE = {"id": "S1", "client_id": 1, "credit_balance": 33600, "down_payment": 10000}


def rows():
    return [
        {"id": 1, "sale_id": "S1", "due_date": "2026-09-01", "amount_expected": 5600, "amount_paid": 5600, "status": "Оплачен"},
        {"id": 2, "sale_id": "S1", "due_date": "2026-10-01", "amount_expected": 5600, "amount_paid": 2000, "status": "Частично"},
        {"id": 3, "sale_id": "S1", "due_date": "2026-11-01", "amount_expected": 5600, "amount_paid": 0, "status": "Не оплачен"},
        {"id": 4, "sale_id": "S1", "due_date": "2026-12-01", "amount_expected": 5600, "amount_paid": 0, "status": "Не оплачен"},
        {"id": 5, "sale_id": "S1", "due_date": "2027-01-01", "amount_expected": 5600, "amount_paid": 0, "status": "Не оплачен"},
        {"id": 6, "sale_id": "S1", "due_date": "2027-02-01", "amount_expected": 5600, "amount_paid": 0, "status": "Не оплачен"},
    ]


def open_draft():
    return [{"id": str(r["id"]), "due": date.fromisoformat(r["due_date"]), "amount": r["amount_expected"]}
            for r in rows() if r["amount_paid"] == 0]


def test_totals_ok():
    t = schedule_totals(33600, rows())
    assert t["ok"] and t["paid"] == 7600 and t["remaining"] == 26000


def test_no_changes():
    plan = plan_schedule_save(SALE, rows(), open_draft(), 33600)
    assert not plan["changed"] and not plan["errors"] and plan["check"]["ok"]


def test_edit_amount_and_date_of_unpaid_row():
    d = open_draft()
    d[0]["amount"] = 4000
    d[0]["due"] = date(2026, 11, 15)
    d.append({"id": None, "due": date(2027, 3, 1), "amount": 1600})
    plan = plan_schedule_save(SALE, rows(), d, 33600)
    assert not plan["errors"]
    assert plan["updates"] == [{"id": 3, "old": {"due_date": "2026-11-01", "amount_expected": 5600, "status": "Не оплачен"},
                                "new": {"due_date": "2026-11-15", "amount_expected": 4000, "status": "Не оплачен"}}]
    assert plan["inserts"][0]["amount_expected"] == 1600 and plan["inserts"][0]["amount_paid"] == 0
    assert plan["check"]["ok"]


def test_delete_unpaid_row_flags_mismatch():
    d = open_draft()[:-1]
    plan = plan_schedule_save(SALE, rows(), d, 33600)
    assert [r["id"] for r in plan["deletes"]] == [6]
    assert not plan["check"]["ok"] and plan["check"]["diff"] == -5600


def test_locked_rows_cannot_be_edited_or_deleted():
    d = open_draft() + [{"id": "1", "due": date(2026, 9, 1), "amount": 1}]
    plan = plan_schedule_save(SALE, rows(), d, 33600)
    assert plan["errors"] and "оплачен" in plan["errors"][0]
    plan2 = plan_schedule_save(SALE, rows(), [], 33600)
    assert {r["id"] for r in plan2["deletes"]} == {3, 4, 5, 6}  # paid 1 and partial 2 untouched


def test_foreign_row_and_bad_values():
    d = [{"id": "999", "due": date(2026, 1, 1), "amount": 5}, {"id": None, "due": None, "amount": 5},
         {"id": None, "due": date(2026, 1, 1), "amount": 0}]
    plan = plan_schedule_save(SALE, rows(), d, 33600)
    assert len(plan["errors"]) == 3


def test_change_credit_balance():
    d = open_draft()
    d[-1]["amount"] = 4600
    plan = plan_schedule_save(SALE, rows(), d, 32600)
    assert plan["contract_update"] == {"old": {"credit_balance": 33600}, "new": {"credit_balance": 32600}}
    assert plan["check"]["ok"]
    bad = plan_schedule_save(SALE, rows(), d, 5000)
    assert any("меньше уже оплаченного" in e for e in bad["errors"])


def test_generate_open_rows():
    out = generate_open_rows(26000 - 3600, 5000, date(2026, 11, 30))
    assert [r["amount"] for r in out] == [5000, 5000, 5000, 5000, 2400]
    assert [r["due"] for r in out][:4] == [date(2026, 11, 30), date(2026, 12, 30), date(2027, 1, 30), date(2027, 2, 28)]
    with pytest.raises(ValueError):
        generate_open_rows(100, 0, date(2026, 1, 1))


def test_annulment_full_and_cash_math():
    now = datetime(2026, 10, 9, 21, 0)
    plan = plan_annulment(rows()[0], 5600, "ошибочная сумма", "Иванов Иван", now)
    assert plan["new"] == {"amount_paid": 0, "status": "Не оплачен"}
    assert plan["cash_entry"]["amount"] == -5600
    assert plan["cash_entry"]["comment"].startswith(ANNUL_PREFIX)
    assert plan["cash_entry"]["date"] == "2026-10-09 21:00"
    cash_before = 50000
    accepted = 5600
    assert cash_before + plan["cash_entry"]["amount"] == cash_before - accepted


def test_annulment_partial_and_validation():
    plan = plan_annulment(rows()[0], 1600, "лишнее", "X")
    assert plan["new"] == {"amount_paid": 4000, "status": "Частично"}
    with pytest.raises(ValueError):
        plan_annulment(rows()[0], 5600, "", "X")
    with pytest.raises(ValueError):
        plan_annulment(rows()[0], 6000, "причина", "X")
    with pytest.raises(ValueError):
        plan_annulment(rows()[2], 100, "причина", "X")


def test_status_for():
    assert status_for(5600, 0) == "Не оплачен"
    assert status_for(5600, 5599.6) == "Оплачен"
    assert status_for(5600, 100) == "Частично"


def test_reuse_ids_turns_relayout_into_updates():
    from installment_logic import reuse_ids
    new = reuse_ids(generate_open_rows(22400, 5000, date(2026, 11, 1)), open_draft())
    assert [r["id"] for r in new] == ["3", "4", "5", "6", None]
    plan = plan_schedule_save(SALE, rows(), new, 33600)
    assert not plan["errors"] and not plan["deletes"] and len(plan["inserts"]) == 1 and plan["check"]["ok"]


def test_rebuild_keeps_paid_rows_and_matches_balance():
    from installment_logic import plan_rebuild_unpaid
    plan = plan_rebuild_unpaid(SALE, rows(), 3, date(2026, 10, 9))
    assert not plan["errors"]
    touched = {u["id"] for u in plan["updates"]} | {r["id"] for r in plan["deletes"]}
    assert not touched & {1, 2}                       # оплаченная и частичная строки не тронуты
    assert {u["id"] for u in plan["updates"]} == {3, 4, 5} and [r["id"] for r in plan["deletes"]] == [6]
    # 33600 - 5600 - 5600 = 22400 на 3 месяца
    new = [u["new"] for u in sorted(plan["updates"], key=lambda u: u["id"])]
    assert [n["amount_expected"] for n in new] == [7467, 7467, 7466]
    assert [n["due_date"] for n in new] == ["2026-11-09", "2026-12-09", "2027-01-09"]
    assert plan["check"]["ok"] and plan["check"]["schedule_total"] == 33600


def test_rebuild_more_months_inserts_and_errors():
    from installment_logic import plan_rebuild_unpaid
    plan = plan_rebuild_unpaid(SALE, rows(), 8, date(2026, 1, 31))
    assert len(plan["inserts"]) == 4 and not plan["deletes"] and plan["check"]["ok"]
    assert plan["updates"][0]["new"]["due_date"] == "2026-02-28"
    paid_all = [dict(r, amount_paid=r["amount_expected"]) for r in rows()]
    with pytest.raises(ValueError):
        plan_rebuild_unpaid(SALE, paid_all, 3, date(2026, 10, 9))
    with pytest.raises(ValueError):
        plan_rebuild_unpaid(SALE, rows(), 0, date(2026, 10, 9))
