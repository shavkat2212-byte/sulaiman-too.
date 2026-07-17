# Магазин «Сулайман-Тоо» — Модуль: Склад
# Версия: 1.6 (восстановлены все функции + Инвентаризация)

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

    # Метрики (только товары с qty > 0)
    df_active = df[df["qty"] > 0] if not df.empty else pd.DataFrame()
    
    total_qty = int(df_active["qty"].sum()) if not df_active.empty else 0
    total_cost = round((df_active["qty"] * df_active["cost"]).sum(), 2) if not df_active.empty else 0
    total_retail = round((df_active["qty"] * df_active["price"]).sum(), 2) if not df_active.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Всего товаров", f"{total_qty} шт.")
    col2.metric("💰 Сумма в закупке", f"{total_cost:,.2f} сом")
    col3.metric("📈 Розничная стоимость", f"{total_retail:,.2f} сом")

    st.markdown("---")

    # ==================== ТАБЛИЦА ТОВАРОВ ====================
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

        present = edited["Наличие"].sum()
        missing = len(edited) - present
        total_sum = edited["Сумма закупки"].sum()

        st.markdown(f"""
        **Итого по инвентаризации:**
        - Всего позиций: **{len(edited)}**
        - Есть: **{present}**
        - Нет: **{missing}**
        - Сумма закупки: **{total_sum:,.2f} сом**
        """)

        # Экспорт
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

    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                upload_df = pd.read_csv(uploaded)
            else:
                upload_df = pd.read_excel(uploaded)

            st.write("Предпросмотр:")
            st.dataframe(upload_df.head())

            if st.button("Загрузить на склад"):
                for _, row in upload_df.iterrows():
                    supabase.table("products").insert({
                        "name": str(row.get("name") or row.get("Товар") or "").lower().strip(),
                        "qty": int(row.get("qty") or row.get("Количество") or 0),
                        "cost": float(row.get("cost") or row.get("Закупка") or 0),
                        "price": float(row.get("price") or row.get("Продажа") or 0),
                        "date": datetime.now().strftime("%Y-%m-%d")
                    }).execute()
                st.success("Товары успешно загружены!")
                st.rerun()
        except Exception as e:
            st.error(f"Ошибка при загрузке: {e}")

    st.markdown("---")

    # ==================== ДОБАВЛЕНИЕ ТОВАРА ВРУЧНУЮ ====================
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

    # ==================== РЕДАКТИРОВАНИЕ / УДАЛЕНИЕ ====================
    st.subheader("✏️ Редактировать / Удалить товар")

    if not df.empty:
        options = {f"{row['name']} | {row['qty']} шт. | {row['date']}": row['id'] for _, row in df.iterrows()}
        selected = st.selectbox("Выберите товар", ["-- Не выбрано --"] + list(options.keys()))

        if selected != "-- Не выбрано --":
            product_id = options[selected]
            product = next((p for p in data if p["id"] == product_id), None)

            if product:
                with st.form("edit_form"):
                    new_name = st.text_input("Название", value=product["name"])
                    new_qty = st.number_input("Количество", min_value=0, value=int(product["qty"]))
                    new_cost = st.number_input("Закупка", value=float(product["cost"]))
                    new_price = st.number_input("Продажа", value=float(product["price"]))

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.form_submit_button("💾 Сохранить изменения"):
                            supabase.table("products").update({
                                "name": new_name.strip().lower(),
                                "qty": new_qty,
                                "cost": new_cost,
                                "price": new_price
                            }).eq("id", product_id).execute()
                            st.success("Изменения сохранены!")
                            st.rerun()
                    with col_b:
                        if st.form_submit_button("🗑️ Удалить товар", type="primary"):
                            supabase.table("products").delete().eq("id", product_id).execute()
                            st.success("Товар удалён!")
                            st.rerun()
