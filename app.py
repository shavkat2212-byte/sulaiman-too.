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
    
    # 1. МАССОВАЯ ЗАГРУЗКА
    st.subheader("📥 Массовая загрузка товаров из Excel (CSV)")
    st.info("Инструкция: создайте Excel с 4 колонками (Название, Кол-во, Закупка, Продажа) и сохраните как CSV.")
    
    uploaded_file = st.file_uploader("Выберите ваш файл .csv", type=["csv"])
    if uploaded_file is not None:
        try:
            raw_bytes = uploaded_file.getvalue()
            file_contents = ""
            for encoding in ("utf-8-sig", "cp1251", "utf-8"):
                try:
                    file_contents = raw_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not file_contents:
                st.error("Не удалось определить кодировку файла.")
            else:
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
    
    # 2. РУЧНОЙ ВВОД И РЕДАКТИРОВАНИЕ (ДВЕ КОЛОНКИ)
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
            # Выбираем товар для редактирования
            edit_list = {n.capitalize(): n for n in data["products"].keys()}
            selected_edit_display = st.selectbox("Выберите товар для изменения", list(edit_list.keys()))
            selected_edit_key = edit_list[selected_edit_display]
            
            # Получаем текущие данные товара
            current_prod = data["products"][selected_edit_key]
            
            with st.form("edit_form"):
                # Поля предзаполнены текущими значениями
                new_qty = st.number_input("Изменить остаток (шт)", min_value=0, value=int(current_prod["qty"]))
                new_cost = st.number_input("Новая цена закупки", min_value=0.0, value=float(current_prod["cost"]))
                new_price = st.number_input("Новая цена продажи", min_value=0.0, value=float(current_prod["price"]))
                
                c_btn1, c_btn2 = st.columns(2)
                save_changes = c_btn1.form_submit_button("💾 Сохранить")
                delete_prod = c_btn2.form_submit_button("🗑️ Удалить товар", type="secondary")
                
                if save_changes:
                    data["products"][selected_edit_key] = {
                        "qty": new_qty,
                        "cost": new_cost,
                        "price": new_price
                    }
                    save_data(data)
                    st.success(f"Товар '{selected_edit_display}' обновлен!")
                    st.rerun()
                    
                if delete_prod:
                    del data["products"][selected_edit_key]
                    save_data(data)
                    st.warning(f"Товар '{selected_edit_display}' удален со склада.")
                    st.rerun()

    st.markdown("---")

    # 3. ТАБЛИЦА ОСТАТКОВ
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
