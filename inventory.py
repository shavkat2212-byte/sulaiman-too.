# Магазин «Сулайман-Тоо» — Модуль: Инвентаризация
# Версия: 1.0 (список с телефона, галочки, Excel)

import io
import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase


def show_inventory_page():
    st.header("Инвентаризация склада")
    st.caption("Отмечай с телефона: товар на месте или нет. Потом скачай Excel.")

    try:
        rows = supabase.table("products").select("*").gt("qty", 0).order("name").execute().data or []
    except Exception as e:
        st.error(f"Не удалось открыть склад: {e}")
        return

    if not rows:
        st.info("На складе нет товаров.")
        return

    if "inv_marks" not in st.session_state:
        st.session_state.inv_marks = {}

    search = st.text_input("Найти товар", placeholder="холодильник, iphone", key="inv_search")
    only_missing = st.checkbox("Показать только где нет", key="inv_only_missing")

    visible = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if search and search.strip().lower() not in name.lower():
            continue
        mark = st.session_state.inv_marks.get(str(row["id"]), True)
        if only_missing and mark:
            continue
        visible.append(row)

    total_qty = sum(int(r.get("qty") or 0) for r in rows)
    total_cost = sum(int(r.get("qty") or 0) * float(r.get("cost") or 0) for r in rows)
    checked = sum(1 for r in rows if st.session_state.inv_marks.get(str(r["id"]), True))
    missing = len(rows) - checked

    c1, c2, c3 = st.columns(3)
    c1.metric("Позиций", f"{len(rows)}")
    c2.metric("Есть", f"{checked}")
    c3.metric("Нет", f"{missing}")
    st.caption(f"Всего {total_qty} шт. на {total_cost:,.0f} сом по закупке")

    b1, b2 = st.columns(2)
    if b1.button("Отметить все как есть", use_container_width=True):
        for row in rows:
            st.session_state.inv_marks[str(row["id"])] = True
        st.rerun()
    if b2.button("Снять все галочки", use_container_width=True):
        for row in rows:
            st.session_state.inv_marks[str(row["id"])] = False
        st.rerun()

    st.markdown("---")
    for row in visible:
        rid = str(row["id"])
        name = str(row.get("name") or "").capitalize()
        qty = int(row.get("qty") or 0)
        cost = float(row.get("cost") or 0)
        date = str(row.get("date") or "")[:10]
        current = st.session_state.inv_marks.get(rid, True)
        left, right = st.columns([4, 1])
        left.markdown(f"**{name}**")
        left.caption(f"{qty} шт. | партия {date} | {qty * cost:,.0f} сом")
        marked = right.checkbox("Есть", value=current, key=f"inv_{rid}")
        st.session_state.inv_marks[rid] = marked

    export_rows = []
    for row in rows:
        rid = str(row["id"])
        qty = int(row.get("qty") or 0)
        cost = float(row.get("cost") or 0)
        price = float(row.get("price") or 0)
        present = st.session_state.inv_marks.get(rid, True)
        export_rows.append({
            "Товар": str(row.get("name") or "").capitalize(),
            "Партия": str(row.get("date") or "")[:10],
            "Остаток по базе": qty,
            "Есть": "Да" if present else "Нет",
            "Закупка": int(cost),
            "Сумма закупки": int(qty * cost),
            "Цена продажи": int(price),
        })
    export_df = pd.DataFrame(export_rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Инвентаризация")
    buffer.seek(0)
    st.download_button(
        "Скачать инвентаризацию в Excel",
        data=buffer.getvalue(),
        file_name=f"Inventarizaciya_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
