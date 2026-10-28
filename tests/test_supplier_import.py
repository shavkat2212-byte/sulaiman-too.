import os
from datetime import datetime
import pytest
import supplier_import as si

D = lambda d: datetime(2026, 8, d)
ROWS = [
    ("Дата", "сом", "$", "Итого", None, None, None),
    (D(1), 1000, 10, 1900, 500, "Икром", None),
    (D(2), 0, 0, 0, 300, "Rodex", None),
    (D(3), 500, None, 500, 200, "Дилшод", "икром?"),
    (None, None, None, 2400, None, None, None),
    (D(30), None, None, None, 700, "Икром Возврат товара", None),
    (D(4), None, None, None, 100, "Икром часы", None),
]


def test_parse():
    p = si.parse_rows(ROWS)
    s = si.summary(p)
    assert s["товар"] == {"count": 2, "sum": 2400.0}
    assert s["оплата"]["count"] == 3  # D1 Икром, D3 (note G), D4 часы
    assert s["возврат"] == {"count": 1, "sum": 700.0}
    assert all("Rodex" not in e["note"] for e in p)
    assert {e["side"] for e in p if e["type"] == "товар"} == {"поставщик"}
    assert p[0]["comment"].startswith("[excel:2026-08-01:товар:1900]")


def test_idempotent():
    p = si.parse_rows(ROWS)
    rows = si.to_rows(p, accepted=True, user={"id": 1, "username": "admin"})
    assert si.new_only(p, rows) == []
    assert len(si.new_only(p, rows[:2])) == len(p) - 2
    assert rows[0]["created_at"] == "2026-08-01T12:00:00+06:00" and rows[0]["accepted"]


@pytest.mark.skipif(not os.path.exists(si.SEED_PATH), reason="no seed")
def test_seed():
    s = si.summary(si.parse_workbook(si.SEED_PATH))
    assert s["товар"]["count"] > 50 and s["возврат"]["count"] == 1
