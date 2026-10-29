# Логика таблицы «Долг с поставщиком» по месяцам (без Streamlit — для тестов).
from datetime import date
import math

MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
             "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
NUM_FIELDS = ("tmz_som", "tmz_usd", "total_goods", "payment", "return_amount")


def num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(v) else v


def ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_label(year_month: str) -> str:
    y, m = year_month.split("-")
    return f"{MONTHS_RU[int(m) - 1]} {y}"


def month_range(start: str, end: str) -> list:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def row_goods(r: dict) -> float:
    """«Итого товар» строки; если пусто — берём «Сумма ТМЗ (сом)»."""
    tg = r.get("total_goods")
    if tg is None or (isinstance(tg, float) and math.isnan(tg)) or tg == "":
        return num(r.get("tmz_som"))
    return num(tg)


def is_empty_row(r: dict) -> bool:
    return (not r.get("row_date") or str(r.get("row_date")) in ("NaT", "None", "")) \
        and all(num(r.get(f)) == 0 for f in NUM_FIELDS) and not str(r.get("comment") or "").strip()


def month_totals(opening, rows) -> dict:
    rows = [r for r in rows if not is_empty_row(r)]
    goods = sum(row_goods(r) for r in rows)
    pay = sum(num(r.get("payment")) for r in rows)
    ret = sum(num(r.get("return_amount")) for r in rows)
    op = num(opening)
    return {"opening": op, "goods": goods, "payment": pay, "returns": ret,
            "closing": op + goods - pay - ret}
