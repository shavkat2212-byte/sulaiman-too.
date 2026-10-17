# Бланк, когда migrations/003_client_documents.sql НЕ выполнена: колонок pin / passport_issued_by / passport_date нет.
import os, sys, types
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COLUMNS = {
    "clients": {"id", "fio", "phone", "address", "passport"},
    "sales": {"id", "date", "day", "name", "client_id", "payment", "total_sale", "down_payment", "credit_balance"},
    "credit_payments": {"id", "sale_id", "client_id", "due_date", "amount_expected", "amount_paid", "status"},
}
DATA = {
    "clients": [{"id": 1, "fio": None, "phone": None, "address": None, "passport": None}],
    "sales": [{"id": "S9", "date": None, "day": None, "name": None, "client_id": 1, "payment": "Рассрочка",
               "total_sale": None, "down_payment": None, "credit_balance": None},
              {"id": "S10", "date": "05.09.2026 10:00", "day": "2026-09-05", "name": "Старый договор без списка товаров",
               "client_id": 99, "payment": "Рассрочка", "total_sale": 12000, "down_payment": 0, "credit_balance": 13200}],
    "credit_payments": [{"id": 1, "sale_id": "S10", "client_id": 99, "due_date": None, "amount_expected": None,
                         "amount_paid": 0, "status": "Не оплачен"}],
}


class APIError(Exception):
    pass


class StrictQuery:
    """Как PostgREST: выбор несуществующей колонки — ошибка."""
    def __init__(self, table):
        self.table, self.filters = table, []

    def select(self, cols="*"):
        if cols != "*":
            bad = [c.strip() for c in cols.split(",") if c.strip() not in COLUMNS[self.table]]
            if bad:
                raise APIError(f"column {self.table}.{bad[0]} does not exist")
        return self

    def eq(self, c, v):
        self.filters.append((c, v)); return self

    def limit(self, n):
        return self

    def execute(self):
        rows = [r for r in DATA[self.table] if all(str(r.get(c)) == str(v) for c, v in self.filters)]
        return types.SimpleNamespace(data=[dict(r) for r in rows])


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    mod = types.ModuleType("database")
    mod.supabase = types.SimpleNamespace(table=lambda t: StrictQuery(t))
    monkeypatch.setitem(sys.modules, "database", mod)
    import streamlit as st
    st.session_state.pop("client_doc_cols", None)
    yield


def test_doc_columns_detected_as_missing():
    from obligation import client_doc_columns_available
    assert client_doc_columns_available() is False


def test_blank_with_all_none_values():
    from obligation import load_sale_data, render_html, build_docx
    d = load_sale_data("S9")
    assert d["fio"] == "" and d["pin"] == "" and d["passport_date"] is None and d["date"] is None
    assert d["total"] == 0 and d["remaining_words"] == "ноль сомов" and d["schedule"] == []
    assert "ОБЯЗАТЕЛЬСТВО" in render_html(d)
    assert build_docx(d)[:2] == b"PK"


def test_blank_without_goods_and_missing_client():
    from obligation import load_sale_data, render_html, build_docx
    d = load_sale_data("S10")
    assert d["goods_name"] == "" and d["goods_qty"] is None and d["fio"] == ""
    assert d["schedule"] == [{"date": None, "amount": 0.0}]
    assert "Итого:" in render_html(d) and build_docx(d)[:2] == b"PK"


def test_missing_sale_raises_clear_error():
    from obligation import load_sale_data
    with pytest.raises(ValueError, match="не найден"):
        load_sale_data("NOPE")
