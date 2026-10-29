from supplier_month_logic import month_totals, month_range, row_goods, month_label


def test_closing_balance():
    rows = [{"row_date": "2026-10-01", "tmz_som": 1000, "total_goods": None, "payment": 0},
            {"row_date": "2026-10-02", "total_goods": 500, "tmz_som": 400, "payment": 300},
            {"row_date": "2026-10-03", "return_amount": 100}]
    t = month_totals(2000, rows)
    assert t["goods"] == 1500 and t["payment"] == 300 and t["returns"] == 100
    assert t["closing"] == 2000 + 1500 - 300 - 100


def test_empty_rows_ignored_and_nan():
    t = month_totals(None, [{"row_date": None, "comment": ""}, {"payment": float("nan"), "total_goods": 10}])
    assert t["closing"] == 10


def test_summary_row_old_month():
    t = month_totals(100, [{"comment": "итого июнь", "total_goods": 900, "payment": 400}])
    assert t["closing"] == 600


def test_helpers():
    assert month_range("2026-11", "2027-02") == ["2026-11", "2026-12", "2027-01", "2027-02"]
    assert row_goods({"total_goods": 0, "tmz_som": 50}) == 0
    assert month_label("2026-10") == "Октябрь 2026"
