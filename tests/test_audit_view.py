import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audit_view import describe, entry_time, filter_rows, journal_rows  # noqa: E402

ENTRIES = [
    {"created_at": "2026-10-09T15:55:00+00:00", "user_name": "shavkat (id 7, Администратор)", "action": "PAYMENT_ANNUL",
     "table_name": "credit_payments", "record_id": "1", "old_data": {"amount_paid": 5600, "status": "Оплачен"},
     "new_data": {"amount_paid": 0, "status": "Не оплачен", "cash_operation_id": 1000, "at": "2026-10-09 21:55"},
     "comment": "Аннулирование оплаты 5600 сом по договору S1: ошибка"},
    {"created_at": "2026-10-01 04:00:00", "user_name": "Администратор", "action": "UPDATE", "table_name": "cash_operations",
     "record_id": "3", "old_data": {"amount": 2000.0, "comment": "x"}, "new_data": {"amount": 2500.0, "comment": "x"},
     "comment": "Редактирование кассовой операции"},
    {"user_name": "shavkat", "action": "SCHEDULE_INSERT", "table_name": "credit_payments", "record_id": "9",
     "old_data": None, "new_data": {"due_date": "2026-11-01", "amount_expected": 3000, "at": "2026-08-15 10:00"}, "comment": "c"},
]


def test_time_is_converted_to_bishkek():
    assert entry_time(ENTRIES[0]) == datetime(2026, 10, 9, 21, 55)
    assert entry_time(ENTRIES[1]) == datetime(2026, 10, 1, 10, 0)
    assert entry_time(ENTRIES[2]) == datetime(2026, 8, 15, 10, 0)  # без created_at — из new_data.at


def test_rows_readable_and_sorted():
    rows = journal_rows(ENTRIES)
    assert [r["ID"] for r in rows] == ["1", "3", "9"]
    assert rows[0]["Действие"] == "Аннулирование оплаты" and rows[0]["Раздел"] == "График платежей"
    assert rows[0]["Было"] == "оплачено: 5 600; статус: Оплачен"
    assert "касса №: 1 000" in rows[0]["Стало"] and "at" not in rows[0]["Стало"]
    assert rows[1]["Было"] == "сумма: 2 000; комментарий: x"
    assert describe(None) == ""


def test_filters():
    rows = journal_rows(ENTRIES)
    assert len(filter_rows(rows, date(2026, 9, 1), date(2026, 10, 31))) == 2
    assert [r["ID"] for r in filter_rows(rows, sections=["Касса"])] == ["3"]
    assert [r["ID"] for r in filter_rows(rows, actions=["График: новый платёж"])] == ["9"]
    assert [r["ID"] for r in filter_rows(rows, user="Администратор")] == ["3"]
    assert [r["ID"] for r in filter_rows(rows, text="S1")] == ["1"]
    assert len(filter_rows(rows, user="Все")) == 3
