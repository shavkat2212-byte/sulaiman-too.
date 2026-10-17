# Новый клиент при рассрочке и перенос договора: python -m pytest tests/
import os, sys, types
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client_logic import find_duplicates, new_client_payload, norm_phone, rename_contract  # noqa: E402

CLIENTS = [{"id": 1, "fio": "Абдижапаров Фирдавсий Илхамжанович", "phone": "0555908884"},
           {"id": 2, "fio": "Петрова Анна", "phone": "+996 700 11-22-33"}]


def test_norm_phone():
    assert norm_phone("0555 90-88-84") == norm_phone("+996555908884") == "555908884"
    assert norm_phone(None) == ""


def test_duplicates_by_phone_and_fio():
    assert [c["id"] for c in find_duplicates(CLIENTS, "Новый Человек", "+996 555 908 884")] == [1]
    assert [c["id"] for c in find_duplicates(CLIENTS, "  петрова   анна ", "")] == [2]
    assert find_duplicates(CLIENTS, "Иванов Иван", "0777 000 000") == []
    assert find_duplicates(CLIENTS, "", "12") == []   # короткий телефон не сравниваем


def test_payload_validation():
    p, err, warn = new_client_payload("  Иванов   Иван ", "", " г. Ош ", "")
    assert p == {"fio": "Иванов Иван", "phone": None, "address": "г. Ош", "passport": None}
    assert not err and any("Телефон" in w for w in warn)
    assert new_client_payload("", "0555", "", "")[1]
    assert any("неполным" in w for w in new_client_payload("Иванов Иван", "0555", "", "")[2])


def test_rename_contract():
    n = "Договор рассрочки №1710 [Телефон (1 шт.)] — Абдижапаров Фирдавсий Илхамжанович"
    assert rename_contract(n, "Абдижапаров Фирдавсий Илхамжанович", "Иванов Иван").endswith("— Иванов Иван")
    assert rename_contract("Старое название", "X", "Y") == "Старое название"


# ---------- перенос договора (фейковая база) ----------
class Q:
    def __init__(self, db, t): self.db, self.t, self.f, self.op, self.payload = db, t, [], "select", None
    def select(self, *a): return self
    def update(self, p): self.op, self.payload = "update", p; return self
    def insert(self, p): self.op, self.payload = "insert", p; return self
    def eq(self, c, v): self.f.append((c, v)); return self
    def execute(self):
        rows = [r for r in self.db[self.t] if all(str(r.get(c)) == str(v) for c, v in self.f)]
        if self.op == "update":
            for r in rows: r.update(self.payload)
        if self.op == "insert":
            self.db[self.t].append(dict(self.payload)); rows = [self.payload]
        return types.SimpleNamespace(data=rows)


@pytest.fixture
def db(monkeypatch):
    data = {"users": [{"id": 7, "username": "shavkat", "role": "Администратор"}],
            "sales": [{"id": "S1", "client_id": 1, "name": "Договор [Телефон (1 шт.)] — Абдижапаров Фирдавсий Илхамжанович"}],
            "credit_payments": [{"id": 1, "sale_id": "S1", "client_id": 1}, {"id": 2, "sale_id": "S1", "client_id": 1},
                                {"id": 3, "sale_id": "S2", "client_id": 1}],
            "audit_log": []}
    mod = types.ModuleType("database")
    mod.supabase = types.SimpleNamespace(table=lambda t: Q(data, t))
    monkeypatch.setitem(sys.modules, "database", mod)
    sys.modules.pop("installment_admin", None)
    import streamlit as st
    st.session_state["user"] = {"id": 7, "username": "shavkat", "role": "Администратор"}
    yield data
    st.session_state.pop("user", None)
    sys.modules.pop("installment_admin", None)


def test_transfer_moves_sale_and_schedule_and_logs(db):
    import installment_admin as ia
    sale = dict(db["sales"][0])
    ia.transfer_contract(sale, CLIENTS[0], {"id": 9, "fio": "Иванов Иван"}, "выбран не тот клиент")
    assert db["sales"][0]["client_id"] == 9 and db["sales"][0]["name"].endswith("— Иванов Иван")
    assert [p["client_id"] for p in db["credit_payments"]] == [9, 9, 1]   # чужой договор не тронут
    log = db["audit_log"][-1]
    assert log["action"] == "CONTRACT_TRANSFER" and log["old_data"]["client_id"] == 1 and log["new_data"]["client_id"] == 9


def test_transfer_needs_reason_and_other_client(db):
    import installment_admin as ia
    with pytest.raises(ValueError):
        ia.transfer_contract(dict(db["sales"][0]), CLIENTS[0], {"id": 9, "fio": "X"}, "")
    with pytest.raises(ValueError):
        ia.transfer_contract(dict(db["sales"][0]), CLIENTS[0], {"id": 1, "fio": "same"}, "причина")


def test_transfer_requires_admin(db):
    import streamlit as st
    import installment_admin as ia
    st.session_state["user"] = {"id": 8, "username": "kassa", "role": "Кассир"}
    with pytest.raises(ia.NotAdmin):
        ia.transfer_contract(dict(db["sales"][0]), CLIENTS[0], {"id": 9, "fio": "X"}, "причина")
