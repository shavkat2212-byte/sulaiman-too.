from datetime import date
from report_logic import period_summary, timing_label


def test_summary():
    clients = [{"id": 1, "fio": "Иванов"}]
    sales = [
        {"payment": "Рассрочка", "date": "05.10.2026 10:00", "client_id": 1, "name": "Д1", "total_sale": 1000, "down_payment": 100, "credit_balance": 1200},
        {"payment": "Рассрочка", "date": "05.09.2026 10:00", "client_id": 1, "total_sale": 500},
        {"payment": "Наличные", "date": "2026-10-06", "total_sale": 300},
    ]
    payments = [{"client_id": 1, "due_date": "2026-10-10", "amount_paid": 400}, {"client_id": 1, "due_date": "2026-11-10", "amount_paid": 0}]
    ops = [
        {"date": "08.10.2026 12:00", "amount": 400, "comment": "Погашение рассрочки от Иванов"},
        {"date": "2026-10-09 12:00", "amount": -50, "comment": "[АННУЛИРОВАНИЕ] x"},
        {"date": "05.10.2026 10:00", "amount": 100, "comment": "Перв. взнос по рассрочке №1 от Иванов"},
        {"date": "10.10.2026", "amount": -70, "comment": "[НУЖДЫ] вода"},
        {"date": "10.10.2026", "amount": -900, "comment": "[ПОСТАВЩИК] Икром"},
        {"date": "10.10.2026", "amount": -5, "comment": "прочее"},
        {"date": "10.11.2026", "amount": -999, "comment": "[НУЖДЫ] вне периода"},
    ]
    products = [{"date": "2026-10-03", "qty": 2, "cost": 150}, {"date": "2026-09-03", "qty": 9, "cost": 1}]
    s = period_summary(date(2026, 10, 1), date(2026, 10, 31), sales, ops, products, payments, clients)
    assert s["issued_count"] == 1 and s["issued_goods"] == 1000 and s["issued_credit"] == 1200
    assert s["repay_count"] == 1 and s["repay_sum"] == 400 and s["repay_net"] == 350
    assert s["repay_rows"][0]["days"] == -2 and s["early"] == 1
    assert s["down_sum"] == 100 and s["cash_sales"] == 300
    assert s["needs"] == 70 and s["supplier"] == 900 and s["other_out"] == 5
    assert s["received_cost"] == 300 and s["received_qty"] == 2


def test_timing_label():
    assert timing_label(0) == "В срок" and timing_label(3) == "Позже на 3 дн." and timing_label(None) == "—"
