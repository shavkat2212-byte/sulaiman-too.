# Тесты изменения срока рассрочки: python -m pytest tests/
import os, sys
from datetime import date
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from installment_logic import plan_restructure, suggest_total, net_debt  # noqa: E402

SALE = {"id": "S1", "client_id": 1, "total_sale": 30000, "down_payment": 2000, "credit_balance": 34720}  # 28000 × 1.24 (8 мес.)


def rows8(paid_count=0):
    out = []
    for i in range(8):
        paid = 4340 if i < paid_count else 0
        out.append({"id": i + 1, "sale_id": "S1", "due_date": f"2026-{11 + i:02d}-10" if i < 2 else f"2027-{i - 1:02d}-10",
                    "amount_expected": 4340, "amount_paid": paid, "status": "Оплачен" if paid else "Не оплачен"})
    return out


def test_suggest_total_markup_by_term():
    assert net_debt(SALE) == 28000
    assert suggest_total(SALE, 8) == 34720
    assert suggest_total(SALE, 6) == 33040  # 28000 × 1.18


def test_8_to_6_months_same_day_recalc():
    plan = plan_restructure(SALE, rows8(), 6, date(2026, 11, 10), suggest_total(SALE, 6))
    assert not plan["errors"]
    amounts = [r["amount"] for r in plan["preview"]]
    assert len(amounts) == 6 and sum(amounts) == 33040
    assert amounts[:5] == [5506] * 5 and amounts[5] == 33040 - 5506 * 5  # остаток в последний месяц
    assert len(plan["updates"]) == 6 and len(plan["deletes"]) == 2 and not plan["inserts"]
    assert plan["contract_update"]["new"]["credit_balance"] == 33040
    assert plan["check"]["ok"]
    assert plan["restructure"]["old"]["months"] == 8 and plan["restructure"]["new"]["months"] == 6


def test_paid_rows_untouched_and_keep_total():
    r = rows8(paid_count=2)
    plan = plan_restructure(SALE, r, 10, date(2027, 1, 10))
    touched = {str(u["id"]) for u in plan["updates"]} | {str(d["id"]) for d in plan["deletes"]}
    assert "1" not in touched and "2" not in touched
    assert plan["contract_update"] is None
    assert sum(x["amount"] for x in plan["preview"]) == 34720 - 2 * 4340
    assert len(plan["preview"]) == 8 and len(plan["inserts"]) == 2
    assert [x["due"] for x in plan["preview"][:2]] == [date(2027, 1, 10), date(2027, 2, 10)]


def test_term_not_longer_than_paid_months():
    with pytest.raises(ValueError):
        plan_restructure(SALE, rows8(paid_count=3), 3, date(2027, 1, 10))


def test_total_below_paid_is_error():
    plan_err = None
    try:
        plan_err = plan_restructure(SALE, rows8(paid_count=2), 6, date(2027, 1, 10), 5000)
    except ValueError:
        return
    assert plan_err["errors"]


from installment_logic import month_schedule, parse_goods, plan_contract_annulment, ANNUL_PREFIX  # noqa: E402


def test_month_schedule_month_end():
    assert month_schedule(date(2026, 1, 31), 4) == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert month_schedule(date(2026, 11, 15), 3) == [date(2026, 11, 15), date(2026, 12, 15), date(2027, 1, 15)]


def test_parse_goods():
    name = "Договор рассрочки №0108-1200 [Холодильник lg (1 шт.), Чайник (2 шт.)] — Иванов Иван"
    assert parse_goods(name) == [("Холодильник lg", 1), ("Чайник", 2)]
    assert parse_goods("без товаров") == []


def test_contract_annulment_plan():
    sale = {**SALE, "payment": "Рассрочка", "name": "Договор [Телефон (1 шт.)] — Иван"}
    plan = plan_contract_annulment(sale, rows8(paid_count=2), "ошибка в договоре", "Иван")
    assert plan["paid"] == 8680 and plan["down"] == 2000 and plan["refund_total"] == 10680
    assert [e["amount"] for e in plan["cash_entries"]] == [-8680, -2000]
    assert all(e["comment"].startswith(ANNUL_PREFIX) for e in plan["cash_entries"])
    assert all(u["new"] == {"amount_paid": 0, "status": "Аннулирован"} for u in plan["row_updates"])
    assert plan["sale_update"]["new"]["payment"] == "Аннулирован"
    assert plan["sale_update"]["new"]["name"].startswith("[АННУЛИРОВАН]")
    assert plan["goods"] == [("Телефон", 1)]


def test_contract_annulment_needs_reason_and_not_twice():
    sale = {**SALE, "payment": "Рассрочка"}
    with pytest.raises(ValueError):
        plan_contract_annulment(sale, rows8(), "", "Иван")
    with pytest.raises(ValueError):
        plan_contract_annulment({**sale, "payment": "Аннулирован"}, rows8(), "причина", "Иван")
