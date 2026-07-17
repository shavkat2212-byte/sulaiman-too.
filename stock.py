# Магазин «Сулайман-Тоо» — Модуль: Склад
# Версия: 1.5 (добавлена Инвентаризация)

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from database import supabase

def show_stock_page():
    st.header("Управление складом")

    # ==================== ЗАГРУЗКА ДАННЫХ ====================
    try:
        response = supabase.table("products").select("*").gt("qty", 0).order("name").execute()
        data = response.data
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return

    if not data:
        st.info("На складе пока нет товаров.")
        return

    df = pd.DataFrame(data)

    # Метрики
    total_qty = int(df["qty"].sum())
    total_cost = round((df["qty"] * df["cost"]).sum(), 2)
    total_retail = round((df["qty"] * df["price"]).sum(), 2)

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Всего товаров", f"{total_qty} шт.")
    col2.metric("💰 Сумма в закупке", f"{total_cost:,.2f} сом")
    col3.metric("📈 Розничная стоимость", f"{total_retail:,.2f} сом")

    st.markdown("---")

    # ==================== ОСНОВНАЯ ТАБЛИЦА ====================
    st.subheader("Список товаров на складе")
    display_df = df[["name", "date", "qty", "cost", "price"]].copy()
    display_df.columns = ["Товар", "Дата поступления", "В наличии", "Закупка", "Продажа"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ==================== ИНВЕНТАРИЗАЦИЯ ====================
    st.subheader("📋 Инвентаризация")

    if st.button("🔍 Начать инвентаризацию", type="primary", use_container_width=True):
        st.session_state["inventory_mode"] = True

    if st.session_state.get("inventory_mode", False):

        st.info("Отметьте галочками товары, которые физически есть на складе")

        # Подготавливаем данные для редактирования
        inv_df = df[["id", "name", "qty", "cost", "price"]].copy()
        inv_df["Сумма закупки"] = inv_df["qty"] * inv_df["cost"]
        inv_df["Наличие"] = True          # по умолчанию всё есть

        inv_df = inv_df.rename(columns={
            "name": "Товар",
            "qty": "Кол-во",
            "cost": "Цена закупки",
            "price": "Цена продажи"
        })

        # Редактируемая таблица с галочками
        edited = st.data_editor(
            inv_df[["Товар", "Кол-во", "Цена закупки", "Цена продажи", "Сумма закупки", "Наличие"]],
            use_container_width=True,
            hide_index=True,
            disabled=["Товар", "Кол-во", "Цена закупки", "Цена продажи", "Сумма закупки"],
            column_config={
                "Наличие": st.column_config.CheckboxColumn(
                    "Есть на складе?",
                    help="Поставьте галочку, если товар физически есть",
                    default=True
                )
            },
            key="inventory_editor"
        )

        # Итоги
        total_sum = edited["Сумма закупки"].sum()
        present_count = edited["Наличие"].sum()
        missing_count = len(edited) - present_count

        st.markdown(f"""
        **Итого:**
        - Всего позиций: **{len(edited)}**
        - Есть в наличии: **{present_count}**
        - Отсутствует: **{missing_count}**
        - Общая сумма закупки: **{total_sum:,.2f} сом**
        """)

        # Экспорт в Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df = edited.copy()
            export_df["Наличие"] = export_df["Наличие"].map({True: "Есть", False: "Нет"})
            export_df.to_excel(writer, index=False, sheet_name="Инвентаризация")
        excel_buffer.seek(0)

        st.download_button(
            label="📥 Скачать отчёт в Excel",
            data=excel_buffer,
            file_name=f"Инвентаризация_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        if st.button("Закрыть инвентаризацию"):
            st.session_state["inventory_mode"] = False
            st.rerun()
