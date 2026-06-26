import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# Файл базы данных
DB_FILE = "sklad_data.json"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"products": {}, "sales": []}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет и Продажи")

menu = st.sidebar.radio("Разделы", ["📦 Склад / Поступление", "💰 Касса / Продажи", "📊 Отчеты по дням"])

def save_product_to_dict(name, qty, cost, price):
    if name in data["products"]:
        data["products"][name]["qty"] += qty
        data["products"][name]["cost"] = cost
        data["products"][name]["price"] = price
    else:
        data["products"][name] = {"qty": qty, "cost": cost, "price": price}

# --- ВКЛАДКА 1: СКЛАД ---
if menu == "📦 Склад / Поступление":
    st.header("Управление товарами")
    
    st.subheader("📥 Массовая загрузка товаров из Excel (.xlsx или .csv)")
    st.info("💡 Теперь можно загружать ОБЫЧНЫЙ файл Excel (.xlsx)! Создайте 4 колонки: Название, Кол-во, Закупка, Продажа. Первая строка — заголовки.")
    
    # Теперь принимаем и csv, и xlsx
    uploaded_file = st.file_uploader("Выберите ваш файл таблицы", type=["csv", "xlsx"])
    if uploaded_file is not None:
        try:
            # Определяем тип файла по его имени
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                try:
                    df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='cp1251')
                except:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8')
            
            if df.shape[1] >= 4:
                imported_count = 0
                for index, row in df.iterrows():
                    try:
                        p_name = str(row.iloc[0]).strip().lower()
                        if not p_name or p_name == 'nan': continue
                            
                        p_qty = int(float(str(row.iloc[1]).strip().replace(' ', '').replace(',', '.')))
                        p_cost = float(str(row.iloc[2]).strip().replace(' ', '').replace(',', '.'))
                        p_price = float(str(row.iloc[3]).strip().replace(' ', '').replace(',', '.'))
                        
                        save_product_to_dict(p_name, p_qty, p_cost, p_price)
                        imported_count += 1
                    except: continue
                
                if imported_count > 0:
                    save_data(data)
                    st.success(f"🚀 Успешно загружено товаров: {imported_count}!")
                    st.rerun()
                else:
                    st.error("В файле не найдено строк с правильными данными. Проверьте, что во 2, 3 и 4 колонках написаны только числа.")
            else:
                st.error("В вашей таблице должно быть как минимум 4 колонки!")
        except Exception as e:
            st.error(f"Не удалось прочитать файл. Ошибка: {e}")

    st.markdown("---")
    
    # 2. РУЧНОЙ ВВОД И РЕДАКТИРОВАНИЕ
    col_add, col_edit = st.columns(2)
    with col_add:
        st.subheader("➕ Добавить один товар вручную")
        with st.form("add_form", clear_on_submit=True):
            name = st.text_input("Название товара").strip().lower()
            qty = st.number_input("Количество (шт)", min_value=1, value=1)
            cost = st.number_input("Закупка (себестоимость)", min_value=0.0)
            price = st.number_input("Цена продажи", min_value=0.0)
            if st.form_submit_button("Добавить"):
                if name:
                    save_product_to_dict(name, qty, cost, price)
                    save_data(data)
                    st.success("Добавлено!")
                    st.rerun()

    with col_edit:
        st.subheader("✏️ Редактировать / Удалить товар")
        if not data["products"]:
            st.write("На складе еще нет товаров для изменения.")
        else:
            edit_list = {n.capitalize(): n for n in data["products"].keys()}
            selected_edit_display = st.selectbox("Выберите товар для изменения", list(edit_list.keys()))
            selected_edit_key = edit_list[selected_edit_display]
            current_prod = data["products"][selected_edit_key]
            
            with st.form("edit_form"):
                new_qty = st.number_input("Изменить остаток (шт)", min_value=0, value=int(current_prod["qty"]))
                new_cost = st.number_input("Новая цена закупки", min_value=0.0, value=float(current_prod["cost"]))
                new_price = st.number_input("Новая цена продажи", min_value=0.0, value=float(current_prod["price"]))
                
                c_btn1, c_btn2 = st.columns(2)
                save_changes = c_btn1.form_submit_button("💾 Сохранить")
                delete_prod = c_btn2.form_submit_button("🗑️ Удалить товар", type="secondary")
                
                if save_changes:
                    data["products"][selected_edit_key] = {"qty": new_qty, "cost": new_cost, "price": new_price}
                    save_data(data)
                    st.success(f"Товар '{selected_edit_display}' updated!")
                    st.rerun()
                if delete_prod:
                    del data["products"][selected_edit_key]
                    save_data(data)
                    st.warning(f"Товар '{selected_edit_display}' удален.")
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Список всех товаров на складе")
    if data["products"]:
        stock_table = []
        for n, info in data["products"].items():
            stock_table.append({
                "Товар": n.capitalize(), "Остаток": info["qty"], 
                "Закупка": info["cost"], "Продажа": info["price"],
                "Сумма (закупка)": info["qty"] * info["cost"]
            })
        st.dataframe(stock_table, use_container_width=True)
    else:
        st.write("Склад пока пуст.")

# --- ОСТАЛЬНЫЕ ВКЛАДКИ (КАССА И ОТЧЕТЫ) ---
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу")
    if not data["products"]:
        st.warning("Сначала добавьте товары на склад.")
    else:
        plist = {n.capitalize(): n for n, i in data["products"].items() if i["qty"] > 0}
        if not plist:
            st.error("Нет товаров в наличии!")
        else:
            sel_display = st.selectbox("Товар", list(plist.keys()))
            sel_key = plist[sel_display]
            prod = data["products"][sel_key]
            st.write(f"Цена: {prod['price']} | Остаток: {prod['qty']}")
            sqty = st.number_input("Количество", min_value=1, max_value=int(prod["qty"]), value=1)
            if st.button("💵 Продать", type="primary"):
                data["products"][sel_key]["qty"] -= sqty
                t_sale, t_cost = sqty * prod["price"], sqty * prod["cost"]
                data["sales"].append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "day": datetime.now().strftime("%Y-%m-%d"),
                    "name": sel_display, "qty": sqty,
                    "total_sale": t_sale, "total_cost": t_cost, "profit": t_sale - t_cost
                })
                save_data(data)
                st.success(f"Продано на {t_sale}!")
                st.rerun()

elif menu == "📊 Отчеты по дням":
    st.header("Аналитика магазина")
    if not data["sales"]:
        st.write("Продаж еще не было.")
    else:
        df = pd.DataFrame(data["sales"])
        c1, c2 = st.columns(2)
        c1.metric("💰 Выручка", f"{df['total_sale'].sum():,.2f}")
        c2.metric("📈 Прибыль", f"{df['profit'].sum():,.2f}")
        st.subheader("Статистика по дням")
        daily = df.groupby("day").agg({"qty": "sum", "total_sale": "sum", "profit": "sum"}).reset_index()
        st.dataframe(daily.sort_values(by="day", ascending=False), use_container_width=True)
