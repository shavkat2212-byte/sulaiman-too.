import streamlit as st
import json
import os
import pandas as pd
import csv
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

# Инициализация сессии
if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

# Настройка веб-страницы
st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет и Продажи")

# Навигационное меню
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
    
    # СДЕЛАЛ ИМПОРТ ГЛАВНЫМ БЛОКОМ (не в спойлере)
    st.subheader("📥 Массовая загрузка товаров из Excel (CSV)")
    st.info("Инструкция: создайте Excel с 4 колонками (Название, Кол-во, Закупка, Продажа) и сохраните как CSV.")
    
    uploaded_file = st.file_uploader("Выберите ваш файл .csv", type=["csv"])
    if uploaded_file is not None:
        try:
            file_contents = uploaded_file.getvalue().decode("utf-8-sig")
            lines = file_contents.splitlines()
            delimiter = ';' if ';' in lines[0] else ','
            reader = csv.reader(lines, delimiter=delimiter)
            
            imported_count = 0
            for row in reader:
                if not row or len(row) < 4: continue
                if any(x in row[0].lower() for x in ["название", "товар", "наименование"]): continue
                
                try:
                    p_name = row[0].strip().lower()
                    p_qty = int(float(row[1].strip().replace(',', '.')))
                    p_cost = float(row[2].strip().replace(',', '.'))
                    p_price = float(row[3].strip().replace(',', '.'))
                    if p_name:
                        save_product_to_dict(p_name, p_qty, p_cost, p_price)
                        imported_count += 1
                except: continue
            
            if imported_count > 0:
                save_data(data)
                st.success(f"Загружено товаров: {imported_count}!")
                st.rerun()
        except Exception as e:
            st.error(f"Ошибка чтения: {e}")

    st.markdown("---") # Разделитель
    
    with st.expander("➕ Добавить один товар вручную"):
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

# --- ОСТАЛЬНЫЕ ВКЛАДКИ ---
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
