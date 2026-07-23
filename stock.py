# Магазин «Сулайман-Тоо» — Модуль: Склад
# Версия: 1.9 (редактирование только для Админа + дата поступления)

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from database import supabase

def show_stock_page():
    st.header("Управление складом")

    user_role = st.session_state.get("user", {}).get("role", "Кассир")

    # ===== ЗАГРУЗКА ДАННЫХ =====
    try:
        response = supabase.table("products").select("*").order("name").execute()
        data = response.data or []
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return

    df = pd.DataFrame(data) if data else pd.DataFrame()
    df_active = df[df["qty"] > 0] if not df.empty else pd.DataFrame()

    # Метрики
    total_qty = int(df_active["qty"].sum()) if not df_active.empty else 0
    total_cost = round((df_active["qty"] * df_active["cost"]).sum(), 2) if not df_active.empty else 0
    total_retail = round((df_active["qty"] * df_active["price"]).sum(), 2) if not df_active.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Всего товаров", f"{total_qty} шт.")
    c2.metric("💰 Сумма в закупке", f"{total_cost:,.2f} сом")
    c3.metric("📈 Розничная стоимость", f"{total_retail:,.2f} сом")

    st.markdown("---")

    # ===== СПИСОК ТОВАРОВ =====
    st.subheader("Список товаров на складе")
    if not df_active.empty:
        display = df_active[["name", "date", "qty", "cost", "price"]].copy()
        display.columns = ["Товар", "Дата поступления", "В наличии", "Закупка", "Продажа"]
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("На складе пока нет товаров.")

    st.markdown("---")

    # ===== ИНВЕНТАРИЗАЦИЯ =====
    st.subheader("📋 Инвентаризация")

    if "inventory_mode" not in st.session_state:
        st.session_state["inventory_mode"] = False

    if st.button("🔍 Начать инвентаризацию", type="primary"):
        st.session_state["inventory_mode"] = True

    if st.session_state["inventory_mode"] and not df_active.empty:
        st.info("Отметьте галочками товары, которые физически есть")

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

        st.markdown(f"**Итого:** Всего {len(edited)} | Есть: {present} | Нет: {missing} | Сумма: {total_sum:,.0f} сом")

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            export = edited.copy()
            export["Наличие"] = export["Наличие"].map({True: "Есть", False: "Нет"})
            export.to_excel(writer, index=False, sheet_name="Инвентаризация")
        buffer.seek(0)

        st.download_button(
            "📥 Скачать отчёт в Excel",
            data=buffer,
            file_name=f"Inventarizaciya_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if st.button("Закрыть инвентаризацию"):
            st.session_state["inventory_mode"] = False
            st.rerun()

    st.markdown("---")

    # ===== ЗАГРУЗКА ИЗ EXCEL =====
    st.subheader("📥 Загрузка товаров из Excel")
    uploaded = st.file_uploader("Выберите файл", type=["xlsx", "xls", "csv"])

    if uploaded is not None:
        try:
            if uploaded.name.endswith(".csv"):
                upload_df = pd.read_csv(uploaded)
            else:
                upload_df = pd.read_excel(uploaded)

            st.write("Столбцы в файле:", list(upload_df.columns))
            st.dataframe(upload_df.head(5))

            col_map = {}
            for col in upload_df.columns:
                cl = str(col).lower().strip()
                if cl in ["name", "товар", "название", "наименование"]:
                    col_map["name"] = col
                elif cl in ["qty", "количество", "кол-во", "кол", "шт"]:
                    col_map["qty"] = col
                elif cl in ["cost", "закупка", "цена закупки", "себестоимость"]:
                    col_map["cost"] = col
                elif cl in ["price", "продажа", "цена продажи", "розница"]:
                    col_map["price"] = col

            if "name" not in col_map:
                st.error("Не найден столбец с названием товара")
            else:
                if st.button("Загрузить на склад", type="primary"):
                    success = 0
                    errors = []
                    for idx, row in upload_df.iterrows():
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
                            success += 1
                        except Exception as e:
                            errors.append(f"Строка {idx+2}: {e}")
                    if success:
                        st.success(f"✅ Загружено: {success} товаров")
                    if errors:
                        st.error(f"Ошибок: {len(errors)}")
                    st.rerun()
        except Exception as e:
            st.error(f"Ошибка чтения файла: {e}")

    st.markdown("---")

    # ===== ДОБАВЛЕНИЕ ВРУЧНУЮ =====
    st.subheader("➕ Добавить товар вручную")

    with st.form("add_form", clear_on_submit=True):
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
                st.warning("Введите название")

    st.markdown("---")

    # ===== РЕДАКТИРОВАНИЕ / УДАЛЕНИЕ (только Админ) =====
    if user_role == "Администратор":
        st.subheader("✏️ Редактировать / Удалить товар")

        if not df.empty:
            options = {
                f"{row['name']} | {int(row['qty'])} шт. | закупка {row['cost']} | {row['date']}": row["id"]
                for _, row in df.iterrows()
            }
            selected = st.selectbox("Выберите товар", ["-- Не выбрано --"] + list(options.keys()))

            if selected != "-- Не выбрано --":
                product_id = options[selected]
                product = next((p for p in data if p["id"] == product_id), None)

                if product:
                    with st.form("edit_product_form"):
                        new_name = st.text_input("Название", value=product["name"])
                        new_qty = st.number_input("Количество", min_value=0, value=int(product["qty"]))
                        new_cost = st.number_input("Цена закупки", value=float(product["cost"]))
                        new_price = st.number_input("Цена продажи", value=float(product["price"]))

                        # Дата поступления
                        try:
                            current_date = datetime.strptime(str(product["date"])[:10], "%Y-%m-%d").date()
                        except:
                            try:
                                current_date = datetime.strptime(str(product["date"])[:10], "%d.%m.%Y").date()
                            except:
                                current_date = datetime.now().date()

                        new_date = st.date_input("Дата поступления (партия)", value=current_date)

                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Сохранить изменения", type="primary"):
                                supabase.table("products").update({
                                    "name": new_name.strip().lower(),
                                    "qty": new_qty,
                                    "cost": new_cost,
                                    "price": new_price,
                                    "date": new_date.strftime("%Y-%m-%d")
                                }).eq("id", product_id).execute()
                                st.success("Изменения сохранены!")
                                st.rerun()
                        with col2:
                            if st.form_submit_button("🗑️ Удалить товар"):
                                supabase.table("products").delete().eq("id", product_id).execute()
                                st.success("Товар удалён!")
                                st.rerun()
        else:
            st.info("Нет товаров для редактирования")
    else:
        st.info("Редактирование товаров доступно только Администратору")
