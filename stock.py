# Магазин «Сулайман-Тоо» — Модуль: Управление складом
# Версия программы: 1.4 (Внедрена защита редактирования остатков для Кассиров)

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
    else:
        st.subheader("📥 Загрузка/Обновление товаров из Excel (.xlsx или .csv)")
        uploaded = st.file_uploader("Выберите файл таблицы", type=["csv", "xlsx"])
        
        if uploaded is not None:
            if st.button("🚀 Загрузить товары из файла на склад", type="primary", use_container_width=True):
                with st.spinner("⏳ Синхронизация с Supabase..."):
                    try:
                        if uploaded.name.endswith(".xlsx"):
                            df = pd.read_excel(uploaded, engine="openpyxl")
                        else:
                            try:
                                df = pd.read_csv(uploaded, encoding="utf-8")
                            except:
                                uploaded.seek(0)
                                df = pd.read_csv(uploaded, sep=None, engine="python", encoding="cp1251")

                        today = datetime.now().strftime("%Y-%m-%d")
                        existing_res = supabase.table("products").select("id", "name").eq("date", today).execute()
                        existing_map = {row["name"]: row["id"] for row in existing_res.data}
                        
                        insert_list = []
                        for idx, row in df.iterrows():
                            try:
                                name_raw = str(row.iloc[0]).strip().lower()
                                if not name_raw or name_raw == "nan": continue
                                qty_raw = int(float(str(row.iloc[1]).replace(" ", "").replace(",", ".")))
                                cost_raw = float(str(row.iloc[2]).replace(" ", "").replace(",", "."))
                                price_raw = float(str(row.iloc[3]).replace(" ", "").replace(",", "."))
                                
                                if name_raw in existing_map:
                                    supabase.table("products").update({"qty": qty_raw, "cost": cost_raw, "price": price_raw}).eq("id", existing_map[name_raw]).execute()
                                else:
                                    insert_list.append({"name": name_raw, "qty": qty_raw, "cost": cost_raw, "price": price_raw, "date": today})
                            except: continue
                        
                        if insert_list:
                            supabase.table("products").insert(insert_list).execute()
                        st.success("🎉 Склад успешно синхронизирован!")
                        st.rerun()
                    except Exception as e: st.error(f"Ошибка чтения файла: {e}")

        st.markdown("---")
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
                            supabase.table("products").update({"qty": qty, "cost": cost, "price": price}).eq("id", existing.data[0]["id"]).execute()
                        else:
                            supabase.table("products").insert({"name": name, "qty": qty, "cost": cost, "price": price, "date": today}).execute()
                        st.success("Успешно сохранено!")
                        st.rerun()

        with col_edit:
            st.subheader("✏️ Редактировать / Удалить партию")
            
            # ЗАЩИТА СКЛАДА: Блокируем форму изменения для кассиров
            if st.session_state.get("user_role") == "Кассир":
                st.warning("🔒 Редактирование, изменение и удаление остатков на складе доступно только Администратору.")
            else:
                if df_stock.empty:
                    st.info("Товаров пока нет")
                else:
                    options = {f"{row['Товар']} | Приход: {row['Дата поступления']}": row["id"] for _, row in df_stock.iterrows()}
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
                                    "name": processed_name, "qty": new_qty, "cost": new_cost, "price": new_price
                                }).eq("id", batch_id).execute()
                                st.success("Изменения успешно сохранены!")
                                st.rerun()
                            else:
                                st.error("Название товара не может быть пустым!")
