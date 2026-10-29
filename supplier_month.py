# Магазин «Сулайман-Тоо» — Долг с поставщиком: таблица по месяцам, как в Excel.
from datetime import date, datetime, timezone
import pandas as pd
import streamlit as st
from database import supabase
import supplier_month_logic as ml

START_MONTH = "2026-06"
MIGRATION_HINT_007 = ("Таблица по месяцам ещё не создана. Администратору нужно один раз выполнить файл "
                      "`migrations/007_supplier_monthly_grid.sql` в Supabase → SQL Editor → Run.")
COLS = {"row_date": "Дата", "tmz_som": "Сумма ТМЗ (сом)", "tmz_usd": "Сумма ТМЗ ($)",
        "total_goods": "Итого товар", "payment": "Оплата", "return_amount": "Возврат",
        "comment": "Комментарий / контрагент"}


def fmt(x) -> str:
    return f"{ml.num(x):,.0f}".replace(",", " ") + " сом"


def load_all():
    """Возвращает (meta{ym: opening}, rows{ym: [..]}) или (None, None), если нет миграции 007."""
    try:
        meta = supabase.table("supplier_month_meta").select("*").execute().data or []
        rows = supabase.table("supplier_day_rows").select("*").order("sort_order").execute().data or []
    except Exception:
        return None, None
    m = {r["year_month"]: ml.num(r.get("opening_balance")) for r in meta}
    by = {}
    for r in rows:
        by.setdefault(r["year_month"], []).append(r)
    return m, by


def _opening_for(month, months, meta, rows):
    """Сохранённый входящий остаток или (подсказка) исходящий прошлого месяца."""
    if month in meta:
        return meta[month], True
    i = months.index(month)
    if i == 0:
        return 0.0, False
    prev = months[i - 1]
    op, _ = _opening_for(prev, months, meta, rows)
    return ml.month_totals(op, rows.get(prev, []))["closing"], False


def _to_df(rows):
    df = pd.DataFrame([{k: r.get(k) for k in COLS} for r in rows], columns=list(COLS))
    df["row_date"] = pd.to_datetime(df["row_date"], errors="coerce").dt.date
    for f in ml.NUM_FIELDS:
        df[f] = pd.to_numeric(df[f], errors="coerce")
    df["comment"] = df["comment"].astype("object")
    return df


def _save(month, opening, df, user):
    recs = []
    for i, r in enumerate(df.to_dict("records")):
        if ml.is_empty_row(r):
            continue
        d = r.get("row_date")
        recs.append({
            "year_month": month,
            "row_date": d.isoformat() if hasattr(d, "isoformat") and not pd.isna(d) else None,
            **{f: (None if pd.isna(r.get(f)) else float(r.get(f))) for f in ml.NUM_FIELDS},
            "comment": (str(r.get("comment")).strip() if r.get("comment") is not None and not pd.isna(r.get("comment")) else None) or None,
            "sort_order": i,
        })
    supabase.table("supplier_month_meta").upsert({
        "year_month": month, "opening_balance": float(opening),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by_name": user.get("username") or user.get("full_name"),
    }).execute()
    supabase.table("supplier_day_rows").delete().eq("year_month", month).execute()
    for i in range(0, len(recs), 100):
        supabase.table("supplier_day_rows").insert(recs[i:i + 100]).execute()
    return len(recs)


def show_monthly_grid(user, can_edit=True):
    meta, rows = load_all()
    if meta is None:
        st.warning(MIGRATION_HINT_007)
        try:
            with st.expander("SQL для миграции 007"):
                st.code(open("migrations/007_supplier_monthly_grid.sql", encoding="utf-8").read(), language="sql")
        except Exception:
            pass
        return
    cur = ml.ym(date.today())
    months = ml.month_range(START_MONTH, max([cur] + list(meta) + list(rows)))

    op_cur, _ = _opening_for(cur, months, meta, rows)
    closing_cur = ml.month_totals(op_cur, rows.get(cur, []))["closing"]
    st.metric(f"Остаток долга на сейчас ({ml.month_label(cur)})", fmt(closing_cur))
    st.caption("Исходящий остаток = Входящий остаток + Итого товар − Оплата − Возврат. "
               "Старые месяцы можно заполнить одной строкой-итогом, текущий — по дням. "
               "После правок нажмите «💾 Сохранить месяц».")

    labels = [ml.month_label(m) for m in months]
    sel = st.radio("Месяц", labels, index=labels.index(ml.month_label(cur)), horizontal=True, key="sup_month_sel")
    month = months[labels.index(sel)]

    opening, saved = _opening_for(month, months, meta, rows)
    op = st.number_input("Входящий остаток на начало месяца, сом", value=float(opening), step=100.0,
                         key=f"sup_open_{month}", disabled=not can_edit)
    if not saved:
        st.caption("↑ Подставлен исходящий остаток прошлого месяца — поправьте при необходимости и сохраните.")

    df = _to_df(rows.get(month, []))
    cfg = {
        "row_date": st.column_config.DateColumn(COLS["row_date"], format="DD.MM.YYYY"),
        "tmz_som": st.column_config.NumberColumn(COLS["tmz_som"], format="%.0f"),
        "tmz_usd": st.column_config.NumberColumn(COLS["tmz_usd"], format="%.2f"),
        "total_goods": st.column_config.NumberColumn(COLS["total_goods"], format="%.0f",
                                                     help="Если пусто — берётся «Сумма ТМЗ (сом)»"),
        "payment": st.column_config.NumberColumn(COLS["payment"], format="%.0f"),
        "return_amount": st.column_config.NumberColumn(COLS["return_amount"], format="%.0f"),
        "comment": st.column_config.TextColumn(COLS["comment"]),
    }
    edited = st.data_editor(df, column_config=cfg, num_rows="dynamic" if can_edit else "fixed",
                            disabled=not can_edit, hide_index=True, width="stretch",
                            key=f"sup_grid_{month}")

    t = ml.month_totals(op, edited.to_dict("records"))
    c = st.columns(5)
    c[0].metric("Входящий остаток", fmt(t["opening"]))
    c[1].metric("Итого товар за месяц", fmt(t["goods"]))
    c[2].metric("Итого оплата за месяц", fmt(t["payment"]))
    c[3].metric("Возврат", fmt(t["returns"]))
    c[4].metric("Исходящий остаток", fmt(t["closing"]))

    if can_edit and st.button("💾 Сохранить месяц", type="primary", key=f"sup_save_{month}"):
        try:
            n = _save(month, op, edited, user)
        except Exception as ex:
            st.error(f"Не удалось сохранить: {ex}")
        else:
            st.session_state.pop(f"sup_grid_{month}", None)
            st.success(f"Сохранено: {ml.month_label(month)}, строк {n}")
            st.rerun()
