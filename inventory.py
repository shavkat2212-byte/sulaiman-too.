# Магазин «Сулайман-Тоо» — Модуль: Инвентаризация
# Версия: 1.2 (галочки сохраняются в базу)

import io
import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase, get_rows


def load_marks():
    try:
        rows = supabase.table("inventory_marks").select("*").execute().data or []
        return {str(r.get("product_id")): bool(r.get("present")) for r in rows}
    except Exception:
        return None


def save_mark(product_id, present):
    supabase.table("inventory_marks").upsert({
        "product_id": str(product_id),
        "present": bool(present),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }).execute()


def show_inventory_page():
    st.header("Инвентаризация склада")
    st.caption("Галочки пустые, пока сам не отметишь. Отметки сохраняются: можно закрыть телефон и продолжить.")

    saved = load_marks()
    if saved is None:
        st.error("Таблица сверки ещё не создана. В Supabase открой SQL Editor и выполни этот текст:")
        st.code(
            "create table if not exists inventory_marks (\n"
            "  product_id text primary key,\n"
            "  present boolean default false,\n"
            "  updated_at text\n"
            ");",
            language="sql",
        )
        saved = {}

    if "inv_loaded" not in st.session_state:
        st.session_state.inv_marks = dict(saved)
        st.session_state.inv_loaded = True
    elif "inv_marks" not in st.session_state:
        st.session_state.inv_marks = dict(saved)

    try:
        rows = [r for r in get_rows("products") if int(r.get("qty") or 0) > 0]
        rows.sort(key=lambda r: str(r.get("name") or ""))
    except Exception as e:
        st.error(f"Не удалось открыть склад: {e}")
        return

    if not rows:
        st.info("На складе нет товаров.")
        return

    search = st.text_input("Найти товар", placeholder="холодильник, iphone", key="inv_search")
    only_found = st.checkbox("Показать только отмеченные", key="inv_only_found")

    visible = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if search and search.strip().lower() not in name.lower():
            continue
        mark = bool(st.session_state.inv_marks.get(str(row["id"]), False))
        if only_found and not mark:
            continue
        visible.append(row)

    total_qty = sum(int(r.get("qty") or 0) for r in rows)
    total_cost = sum(int(r.get("qty") or 0) * float(r.get("cost") or 0) for r in rows)
    found = sum(1 for r in rows if st.session_state.inv_marks.get(str(r["id"]), False))
    not_found = len(rows) - found

    c1, c2, c3 = st.columns(3)
    c1.metric("Позиций", f"{len(rows)}")
    c2.metric("Отмечено", f"{found}")
    c3.metric("Ещё не найдено", f"{not_found}")
    st.caption(f"Всего {total_qty} шт. на {total_cost:,.0f} сом по закупке")

    b1, b2 = st.columns(2)
    if b1.button("Снять все галочки", use_container_width=True):
        try:
            for row in rows:
                st.session_state.inv_marks[str(row["id"])] = False
                save_mark(row["id"], False)
            st.rerun()
        except Exception as e:
            st.error(f"Не сохранилось: {e}")
    if b2.button("Новая сверка", use_container_width=True):
        try:
            for row in rows:
                st.session_state.inv_marks[str(row["id"])] = False
                save_mark(row["id"], False)
            st.session_state.inv_loaded = True
            st.rerun()
        except Exception as e:
            st.error(f"Не сохранилось: {e}")

    st.markdown("---")
    for row in visible:
        rid = str(row["id"])
        name = str(row.get("name") or "").capitalize()
        qty = int(row.get("qty") or 0)
        cost = float(row.get("cost") or 0)
        date = str(row.get("date") or "")[:10]
        current = bool(st.session_state.inv_marks.get(rid, False))
        left, right = st.columns([4, 1])
        left.markdown(f"**{name}**")
        left.caption(f"{qty} шт. | партия {date} | {qty * cost:,.0f} сом")
        marked = right.checkbox("Есть", value=current, key=f"inv_{rid}")
        if marked != current:
            st.session_state.inv_marks[rid] = marked
            try:
                save_mark(rid, marked)
            except Exception as e:
                st.error(f"Галочка не сохранилась: {e}")

    export_rows = []
    for row in rows:
        rid = str(row["id"])
        qty = int(row.get("qty") or 0)
        cost = float(row.get("cost") or 0)
        price = float(row.get("price") or 0)
        present = bool(st.session_state.inv_marks.get(rid, False))
        export_rows.append({
            "Товар": str(row.get("name") or "").capitalize(),
            "Партия": str(row.get("date") or "")[:10],
            "Остаток по базе": qty,
            "Есть": "Да" if present else "Нет",
            "Закупка": int(cost),
            "Сумма закупки": int(qty * cost),
            "Цена продажи": int(price),
        })
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(export_rows).to_excel(writer, index=False, sheet_name="Инвентаризация")
    buffer.seek(0)
    st.download_button(
        "Скачать инвентаризацию в Excel",
        data=buffer.getvalue(),
        file_name=f"Inventarizaciya_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
