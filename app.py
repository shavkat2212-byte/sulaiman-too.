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

# Инициализация сессии
if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

# Настройка веб-страницы
st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет и Продажи")

# Навигационное меню в боковой панели
menu = st.sidebar.radio("Навигация по системе", ["📋 Склад и Приход", "🛒 Оформление Продаж", "📈 Финансовые Отчеты"])

# --- ВКЛАДКА 1: СКЛАД ---
if menu == "📋 Склад и Приход":
    st.header("Управление остатками и поступлениями")
    
    with st.expander("➕ Добавить новый товар (или увеличить остаток)"):
        with st.form("add_form", clear_on_submit=True):
            name = st.text_input("Название товара (например: Футболка черная L)").strip().lower()
            qty = st.number_input("Количество (шт)", min_value=1, value=10, step=1)
            cost = st.number_input("Себестоимость за 1 шт (закупка)", min_value=0.0, value=500.0, step=50.0)
            price = st.number_input("Цена продажи за 1 шт", min_value=0.0, value=1200.0, step=50.0)
            submit = st.form_submit_button("Занести на склад")
            
            if submit and name:
                if name in data["products"]:
                    data["products"][name]["qty"] += qty
                    data["products"][name]["cost"] = cost
                    data["products"][name]["price"] = price
                else:
                    data["products"][name] = {"qty": qty, "cost": cost, "price": price}
                save_data(data)
                st.success(f"Товар '{name.capitalize()}' успешно обновлен!")
                st.rerun()

    st.subheader("Текущие запасы на складе")
    if data["products"]:
        stock_list = []
        total_stock_cost = 0.0
        for n, info in data["products"].items():
            item_total = info["qty"] * info["cost"]
            total_stock_cost += item_total
            stock_list.append({
                "Товар": n.capitalize(),
                "Остаток (шт)": info["qty"],
                "Себестоимость (руб)": round(info["cost"], 2),
                "Цена продажи (руб)": round(info["price"], 2),
                "Стоимость остатка (руб)": round(item_total, 2)
            })
        df_stock = pd.DataFrame(stock_list)
        st.dataframe(df_stock, use_container_width=True)
        st.info(f"Общая стоимость всех товаров на складе по закупке: **{total_stock_cost:,.2f} руб.**")
    else:
        st.write("На складе пока нет товаров. Добавьте первый товар выше.")

# --- ВКЛАДКА 2: ПРОДАЖИ ---
elif menu == "🛒 Оформление Продаж":
    st.header("Регистрация продаж и списание")
    
    if not data["products"] or sum(p["qty"] for p in data["products"].values()) == 0:
        st.warning("На складе нет доступных товаров для продажи. Сначала добавьте товары на склад.")
    else:
        available_products = {n.capitalize(): n for n, info in data["products"].items() if info["qty"] > 0}
        
        if not available_products:
            st.error("Все товары закончились на складе!")
        else:
            selected_display = st.selectbox("Выберите товар для продажи", list(available_products.keys()))
            selected_key = available_products[selected_display]
            
            prod_info = data["products"][selected_key]
            st.write(f"💵 Цена продажи: **{prod_info['price']} руб.** | 📦 Остаток: **{prod_info['qty']} шт.**")
            
            qty_to_sell = st.number_input("Сколько штук продано?", min_value=1, max_value=int(prod_info["qty"]), value=1, step=1)
            
            if st.button("🔥 Оформить продажу", type="primary"):
                data["products"][selected_key]["qty"] -= qty_to_sell
                
                t_sale = qty_to_sell * prod_info["price"]
                t_cost = qty_to_sell * prod_info["cost"]
                
                sale_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "day": datetime.now().strftime("%Y-%m-%d"),
                    "name": selected_key.capitalize(),
                    "qty": qty_to_sell,
                    "total_sale": t_sale,
                    "total_cost": t_cost,
                    "profit": t_sale - t_cost
                }
                data["sales"].append(sale_entry)
                save_data(data)
                st.success(f"Продано {qty_to_sell} шт. на сумму {t_sale:,.2f} руб. Остаток обновлен!")
                st.rerun()

    st.subheader("История последних операций")
    if data["sales"]:
        df_sales = pd.DataFrame(data["sales"])
        df_sales = df_sales.rename(columns={
            "date": "Дата/Время", "day": "День", "name": "Товар", 
            "qty": "Кол-во", "total_sale": "Выручка", "total_cost": "Себест.", "profit": "Прибыль"
        })
        st.dataframe(df_sales.iloc[::-1], use_container_width=True)
    else:
        st.write("Продаж за последнее время не зафиксировано.")

# --- ВКЛАДКА 3: ОТЧЕТЫ ---
elif menu == "📈 Финансовые Отчеты":
    st.header("Аналитика доходов и маржинальности")
    
    if not data["sales"]:
        st.info("Недостаточно данных для отчетов. Оформите хотя бы одну продажу.")
    else:
        sales_df = pd.DataFrame(data["sales"])
        total_rev = sales_df["total_sale"].sum()
        total_prf = sales_df["profit"].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Общая Выручка", f"{total_rev:,.2f} руб.")
        c2.metric("📈 Чистая Прибыль", f"{total_prf:,.2f} руб.", delta=f"{round((total_prf/total_rev)*100, 1)}% маржа" if total_rev > 0 else None)
        c3.metric("📦 Всего продано (шт)", f"{int(sales_df['qty'].sum())} шт.")
        
        st.subheader("📊 Результаты работы по дням")
        daily = sales_df.groupby("day").agg({
            "qty": "sum",
            "total_sale": "sum",
            "profit": "sum"
        }).reset_index()
        
        daily = daily.rename(columns={
            "day": "Дата", "qty": "Продано штук", "total_sale": "Выручка за день", "profit": "Чистая прибыль"
        }).sort_values(by="Дата", ascending=False)
        
        st.dataframe(daily, use_container_width=True)
