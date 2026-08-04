# Магазин «Сулайман-Тоо» — Модуль: Управление складом
# Версия: 1.5 (умная загрузка Excel + предпросмотр)

import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def db_get_stock():
    response = supabase.table("products").select("*").gt("qty", 0).execute()
    flat = []
    total_qty = total_cost = total_retail = 0.0
    for row in response.data:
        qty = int(row["qty"])
        cost = float(row["cost"])
        price = float(row["price"])
        flat.append({
            "id": row["id"],
            "Товар": str(row["name"]).capitalize(),
            "Дата поступления": row["date"],
            "В наличии (шт)": qty,
            "Закупка (сом)": cost,
            "Продажа (сом)": price,
            "Себестоимость партии (сом)": round(qty * cost, 2)
        })
        total_qty += qty
        total_cost += qty * cost
        total_retail += qty * price
    return pd.DataFrame(flat), total_qty, total_cost, total_retail

def show_stock_page():
    st.header("Управление складом")
    df_stock, total_qty, total_cost, total_retail = db_get_stock()

    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Всего товаров в наличии", f"{int(total_qty)} шт.")
    c2.metric("💰 Сумма склада в закупке", f"{total_cost:,.2f} сом")
    c3.metric("📈 Розничная стоимость склада", f"{total_retail:,.2f} сом")

    print_mode = st.checkbox("🖨️ Режим для печати отчёта")

    if print_mode:
        st.subheader("📄 ОТЧЁТ ПО ОСТАТКАМ ТОВАРОВ НА СКЛАДЕ")
        if not df_stock.empty:
            df_print = df_stock.copy().drop(columns=["id"], errors="ignore")
            df_print["Закупка (сом)"] = df_print["Закупка (сом)"].map('{:,.2f} сом'.format)
            df_print["Продажа (сом)"] = df_print["Продажа (сом)"].map('{:,.2f} сом'.format)
            df_print["Себестоимость партии (сом)"] = df_print["Себестоимость партии (сом)"].map('{:,.2f} сом'.format)
            st.table(df_print)
        else:
            st.info("Склад пуст")
        return

    # =====================================================================
    # ЗАГРУЗКА ИЗ EXCEL
    # =====================================================================
    st.subheader("📥 Загрузка/Обновление товаров из Excel (.xlsx или .csv)")
    uploaded = st.file_uploader("Выберите файл таблицы", type=["csv", "xlsx"])

    if uploaded is not None:
        try:
            if uploaded.name.endswith(".xlsx"):
                df = pd.read_excel(uploaded, engine="openpyxl")
            else:
                try:
                    df = pd.read_csv(uploaded, encoding="utf-8")
                except:
                    uploaded.seek(0)
                    df = pd.read_csv(uploaded, sep=None, engine="python", encoding="cp1251")

            st.write("**Предпросмотр файла:**")
            st.dataframe(df.head(15), use_container_width=True)

            cols = [str(c).strip().lower() for c in df.columns]

            def find_col(variants):
                for v in variants:
                    for i, c in enumerate(cols):
                        if v in c:
                            return i
                return None

            name_idx = find_col(["товар", "название", "name", "наименование"])
            qty_idx = find_col(["кол", "qty", "количество", "шт"])
            cost_idx = find_col(["себес", "закуп", "cost", "закупочная"])
            price_idx = find_col(["прод", "price", "розниц", "цена"])

            if name_idx is None:
                name_idx = 0
            if qty_idx is None:
                qty_idx = 1
            if cost_idx is None:
                cost_idx = 2
            if price_idx is None:
                price_idx = 3

            st.caption(
                f"Столбцы: Название=№{name_idx+1}, Кол-во=№{qty_idx+1}, "
                f"Закупка=№{cost_idx+1}, Продажа=№{price_idx+1}"
            )

            parsed = []
            errors = []

            for idx, row in df.iterrows():
                try:
                    name_raw = str(row.iloc[name_idx]).strip().lower()
                    if not name_raw or name_raw in ("nan", "товар", "название"):
                        continue

                    qty_raw = int(float(str(row.iloc[qty_idx]).replace(" ", "").replace(",", ".")))
                    cost_raw = float(str(row.iloc[cost_idx]).replace(" ", "").replace(",", "."))
                    price_raw = float(str(row.iloc[price_idx]).replace(" ", "").replace(",", "."))

                    if qty_raw <= 0:
                        errors.append(f"Строка {idx+2}: количество ≤ 0 — пропущено")
                        continue
                    if cost_raw <= 0 and price_raw <= 0:
                        errors.append(f"Строка {idx+2}: закупка и продажа = 0 — пропущено ({name_raw})")
                        continue

                    parsed.append({
                        "name": name_raw,
                        "qty": qty_raw,
                        "cost": cost_raw,
                        "price": price_raw
                    })
                except Exception as e:
                    errors.append(f"Строка {idx+2}: ошибка — {e}")

            if parsed:
                st.success(f"Готово к загрузке: **{len(parsed)}** товаров")
                st.dataframe(pd.DataFrame(parsed), use_container_width=True, hide_index=True)
            else:
                st.error("Не удалось прочитать ни одного товара")

            if errors:
                with st.expander(f"⚠️ Ошибки ({len(errors)})"):
                    for e in errors:
                        st.write(e)

            if parsed and st.button("🚀 Загрузить товары на склад", type="primary", use_container_width=True):
                today = datetime.now().strftime("%Y-%m-%d")
                existing_res = supabase.table("products").select("id", "name").eq("date", today).execute()
                existing_map = {row["name"]: row["id"] for row in (existing_res.data or [])}

                insert_list = []
                updated = 0
                for item in parsed:
                    if item["name"] in existing_map:
                        supabase.table("products").update({
                            "qty": item["qty"],
                            "cost": item["cost"],
                            "price": item["price"]
                        }).eq("id", existing_map[item["name"]]).execute()
                        updated += 1
                    else:
                        insert_list.append({
                            "name": item["name"],
                            "qty": item["qty"],
                            "cost": item["cost"],
                            "price": item["price"],
                            "date": today
                        })

                if insert_list:
                    supabase.table("products").insert(insert_list).execute()

                st.success(f"✅ Добавлено: {len(insert_list)}, обновлено: {updated}")
                st.rerun()

        except Exception as e:
            st.error(f"Ошибка чтения файла: {e}")

    st.markdown("---")

    # =====================================================================
    # РУЧНОЕ ДОБАВЛЕНИЕ И РЕДАКТИРОВАНИЕ
    # =====================================================================
    col_add, col_edit = st.columns(2)

    with col_add:
        st.subheader("➕ Добавить товар вручную")
        with st.form("add_form", clear_on_submit=True):
            name = st.text_input("Название товара").strip().lower()
            qty = st.number_input("Количество", min_value=1, value=1)
            cost = st.number_input("Закупка (сом)", min_value=0.0, step=10.0)
            price = st.number_input("Цена продажи, сом", min_value=0.0, step=10.0)
            if st.form_submit_button("Сохранить в облако"):
                if name:
                    today = datetime.now().strftime("%Y-%m-%d")
                    existing = supabase.table("products").select("*").eq("name", name).eq("date", today).execute()
                    if existing.data:
                        supabase.table("products").update({
                            "qty": qty, "cost": cost, "price": price
                        }).eq("id", existing.data[0]["id"]).execute()
                    else:
                        supabase.table("products").insert({
                            "name": name, "qty": qty, "cost": cost, "price": price, "date": today
                        }).execute()
                    st.success("Успешно сохранено!")
                    st.rerun()

    with col_edit:
        st.subheader("✏️ Редактировать / Удалить партию")
        if df_stock.empty:
            st.info("Товаров пока нет")
        else:
            options = {
                f"{row['Товар']} | Приход: {row['Дата поступления']}": row["id"]
                for _, row in df_stock.iterrows()
            }
            selected = st.selectbox("Выберите запись", list(options.keys()))
            batch_id = options[selected]
            item_data = supabase.table("products").select("*").eq("id", batch_id).execute().data[0]

            with st.form("edit_form"):
                new_name = st.text_input("Название товара", value=str(item_data["name"]).capitalize())
                new_qty = st.number_input("Изменить остаток (шт)", min_value=0, value=int(item_data["qty"]))
                new_cost = st.number_input("Цена закупки", min_value=0.0, value=float(item_data["cost"]))
                new_price = st.number_input("Цена продажи", min_value=0.0, value=float(item_data["price"]))

                if st.form_submit_button("💾 Сохранить изменения"):
                    if new_name.strip():
                        processed_name = new_name.strip().lower()
                        supabase.table("products").update({
                            "name": processed_name,
                            "qty": new_qty,
                            "cost": new_cost,
                            "price": new_price
                        }).eq("id", batch_id).execute()
                        st.success("Изменения успешно сохранены!")
                        st.rerun()
                    else:
                        st.error("Название товара не может быть пустым!")

    st.markdown("---")
    st.subheader("📋 Товары на складе")
    if not df_stock.empty:
        st.dataframe(
            df_stock.drop(columns=["id"], errors="ignore"),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Склад пуст")
