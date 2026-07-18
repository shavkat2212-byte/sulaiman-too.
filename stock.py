# Магазин «Сулайман-Тоо» — Модуль: Склад
# Версия: 1.7 (все функции + инвентаризация + исправленная загрузка Excel)

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from database import supabase

def show_stock_page():
    st.header("Управление складом")

    # ==================== ЗАГРУЗКА ДАННЫХ ====================
    try:
        response = supabase.table("products").select("*").order("name").execute()
        data = response.data
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return

    df = pd.DataFrame(data) if data else pd.DataFrame()
    df_active = df[df["qty"] > 0] if not df.empty else pd.DataFrame()

    # Метрики
    total_qty = int(df_active["qty"].sum()) if not df_active.empty else 0
    total_cost = round((df_active["qty"] * df_active["cost"]).sum(), 2) if not df_active.empty else 0
    total_retail = round((df_active["qty"] * df_active["price"]).sum(), 2) if not df_active.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Всего товаров", f"{total_qty} шт.")
    col2.metric("💰 Сумма в закупке", f"{total_cost:,.2f} сом")
    col3.metric("📈 Розничная стоимость", f"{total_retail:,.2f} сом")

    st.markdown("---")

    # ==================== ТАБЛИЦА ====================
    st.subheader("Список товаров на складе")
    if not df_active.empty:
        display_df = df_active[["name", "date", "qty", "cost", "price"]].copy()
        display_df.columns = ["Товар", "Дата поступления", "В наличии", "Закупка", "Продажа"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("На складе пока нет товаров.")

    st.markdown("---")

    # ==================== ИНВЕНТАРИЗАЦИЯ ====================
    st.subheader("📋 Инвентаризация")

    if "inventory_mode" not in st.session_state:
        st.session_state["inventory_mode"] = False

    if st.button("🔍 Начать инвентаризацию", type="primary"):
        st.session_state["inventory_mode"] = True

    if st.session_state["inventory_mode"] and not df_active.empty:
        st.info("Отметьте галочками товары, которые физически есть на складе")

        inv_df = df_active[["name", "qty", "cost", "price"]].copy()
        inv_df["Сумма закупки"] = inv_df["qty"] * inv_df["cost"]
        inv_df["Наличие"] = True
        inv_df = inv_df.rename(columns={
            "name": "Товар",
            "qty": "Кол-во",
            "cost": "Цена закупки",
            "price": "Цена продажи"
        })

        edited = st.data_editor(
            inv_df,
            use_container_width=True,
            hide_index=True,
            disabled=["Товар", "Кол-во", "Цена закупки", "Цена продажи", "Сумма закупки"],
            column_config={
                "Наличие": st.column_config.CheckboxColumn("Есть на складе?", default=True)
            },
            key="inventory_editor"
        )

        present = int(edited["Наличие"].sum())
        missing = len(edited) - present
        total_sum = edited["Сумма закупки"].sum()

        st.markdown(f"""
        **Итого:**
        - Всего позиций: **{len(edited)}**
        - Есть: **{present}**
        - Нет: **{missing}**
        - Сумма закупки: **{total_sum:,.2f} сом**
        """)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            export = edited.copy()
            export["Наличие"] = export["Наличие"].map({True: "Есть", False: "Нет"})
            export.to_excel(writer, index=False, sheet_name="Инвентаризация")
        buffer.seek(0)

        st.download_button(
            "📥 Скачать отчёт в Excel",
            data=buffer,
            file_name=f"Инвентаризация_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if st.button("Закрыть инвентаризацию"):
            st.session_state["inventory_mode"] = False
            st.rerun()

    st.markdown("---")

    # ==================== ЗАГРУЗКА ИЗ EXCEL ====================
    st.subheader("📥 Загрузка товаров из Excel")
    uploaded = st.file_uploader("Выберите файл Excel", type=["xlsx", "xls", "csv"])

    if uploaded is not None:
        try:
            if uploaded.name.endswith(".csv"):
                upload_df = pd.read_csv(uploaded)
            else:
                upload_df = pd.read_excel(uploaded)

            st.write("Найденные столбцы:", list(upload_df.columns))
            st.dataframe(upload_df.head(8))

            col_map = {}
            for col in upload_df.columns:
                col_lower = str(col).lower().strip()
                if col_lower in ["name", "товар", "название", "наименование"]:
                    col_map["name"] = col
                elif col_lower in ["qty", "количество", "кол-во", "кол", "шт"]:
                    col_map["qty"] = col
                elif col_lower in ["cost", "закупка", "цена закупки", "себестоимость"]:
                    col_map["cost"] = col
                elif col_lower in ["price", "продажа", "цена продажи", "розница"]:
                    col_map["price"] = col

            st.write("Сопоставленные столбцы:", col_map)

            if "name" not in col_map:
                st.error("Не найден столбец с названием товара")
            else:
                if st.button("Загрузить на склад", type="primary"):
                    success_count = 0
                    error_list = []

                    for index, row in upload_df.iterrows():
                        try:
                            name = str(row[col_map["name"]]).strip().lower()
                            if not name or name == "nan":
                                continue

                            qty = int(float(row.get(col_map.get("qty"), 0) or 0))
                            cost = float(row.get(col_map.get("cost"), 0) or 0)
                            price = float(row.get(col_map.get("price"), 0) or 0)

                            if qty <= 0:
                                continue

                            supabase.table("products").insert({
                                "name": name,
                                "qty": qty,
                                "cost": cost,
                                "price": price,
                                "date": datetime.now().strftime("%Y-%m-%d")
                            }).execute()
                            success_count += 1
                        except Exception as e:
                            error_list.append(f"Строка {index+2}: {e}")

                    if success_count > 0:
                        st.success(f"✅ Успешно загружено: {success_count} товаров")
                    if error_list:
                        st.error(f"Ошибок: {len(error_list)}")
                        with st.expander("Подробности ошибок"):
                            for err in error_list:
                                st.write(err)
                    st.rerun()
        except Exception as e:
            st.error(f"Ошибка чтения файла: {e}")

    st.markdown("---")

    # ==================== ДОБАВЛЕНИЕ ВРУЧНУЮ ====================
    st.subheader("➕ Добавить товар вручную")

    with st.form("add_product_form", clear_on_submit=True):
        name = st.text_input("Название товара")
        qty = st.number_input("Количество", min_value=1, value=1)
        cost = st.number_input("Цена закупки", min_value=0.0, value=0.0)
        price = st.number_input("Цена продажи", min_value=0.0, value=0.0)

        if st.form_submit_button("Добавить на склад"):
            if name.strip():
                supabase.table("products").insert({
                    "name": name.strip().lower(),
                    "qty": qty,
                    "cost": cost,
                    "price": price,
                    "date": datetime.now().strftime("%Y-%m-%d")
                }).execute()
                st.success(f"Товар «{name}» добавлен!")
                st.rerun()
            else:
                st.warning("Введите название товара")

    st.markdown("---")

    # ==================== РЕДАКТИРОВАНИЕ ====================
