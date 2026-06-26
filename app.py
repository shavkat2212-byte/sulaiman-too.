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

# Навигационное меню
menu = st.sidebar.radio("Разделы", ["📦 Склад / Поступление", "💰 Касса / Продажи", "📊 Отчеты по дням"])

# Кнопка очистки данных в боковой панели
st.sidebar.markdown("---")
st.sidebar.subheader("Настройки системы")
if st.sidebar.button("⚠️ Полная очистка склада", type="secondary", help="Удалит все товары и историю продаж"):
    data = {"products": {}, "sales": []}
    st.session_state.data = data
    save_data(data)
    st.sidebar.success("База данных успешно очищена!")
    st.rerun()

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
    
    # ФИКС: Показываем только те товары, у которых остаток больше 0
    active_products = {n: info for n, info in data["products"].items() if info["qty"] > 0}
    
    # НОВОЕ: Отображение общих итогов над данными в виде карточек
    st.subheader("📊 Общие итоги по складу")
    if active_products:
        total_qty = sum(info["qty"] for info in active_products.values())
        total_cost_sum = sum(info["qty"] * info["cost"] for info in active_products.values())
        total_price_sum = sum(info["qty"] * info["price"] for info in active_products.values())
        
        m1, m2, m3 = st.columns(3)
        m1.metric("📦 Всего товаров на складе", f"{total_qty} шт.")
        m2.metric("💰 Общая сумма в закупке", f"{total_cost_sum:,.2f} руб.")
        m3.metric("📈 Потенциальная выручка (в продажах)", f"{total_price_sum:,.2f} руб.")
    else:
        st.info("Склад пуст, итоговые показатели появятся после загрузки товаров.")
        
    st.markdown("---")

    # 1. МАССОВАЯ ЗАГРУЗКА
    st.subheader("📥 Массовая загрузка товаров из Excel (.xlsx или .csv)")
    uploaded_file = st.file_uploader("Выберите ваш файл таблицы", type=["csv", "xlsx"])
    if uploaded_file is not None:
        try:
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
                        
                        data["products"][p_name] = {"qty": p_qty, "cost": p_cost, "price": p_price}
                        imported_count += 1
                    except: continue
                
                if imported_count > 0:
                    save_data(data)
                    st.success(f"🚀 Успешно загружено товаров: {imported_count}!")
                    st.rerun()
        except Exception as e:
            st.error(f"Не удалось прочитать файл: {e}")

    st.markdown("---")
    
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
                    st.success(f"Товар '{selected_edit_display}' обновлен!")
                    st.rerun()
                if delete_prod:
                    del data["products"][selected_edit_key]
                    save_data(data)
                    st.warning(f"Товар '{selected_edit_display}' удален.")
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Список всех товаров на складе")
    if active_products:
        stock_table = []
        for n, info in active_products.items():
            stock_table.append({
                "Товар": n.capitalize(), "Остаток": info["qty"], 
                "Закупка": info["cost"], "Продажа": info["price"],
                "Сумма (закупка)": info["qty"] * info["cost"]
            })
        st.dataframe(stock_table, use_container_width=True)
    else:
        st.write("Склад пуст или все товары распроданы.")

# --- ВКЛАДКА 2: КАССА (ОБНОВЛЕННАЯ) ---
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу")
    if not data["products"]:
        st.warning("Сначала добавьте товары на склад.")
    else:
        # Берем только те товары, которые реально есть в наличии
        plist = {n.capitalize(): n for n, i in data["products"].items() if i["qty"] > 0}
        if not plist:
            st.error("Нет товаров в наличии!")
        else:
            # ИСПРАВЛЕНО: Теперь поиск встроен прямо в выпадающий список (selectbox в Streamlit поддерживает ввод текста для поиска)
            sel_display = st.selectbox("🔍 Начните вводить название товара для поиска", list(plist.keys()))
            sel_key = plist[sel_display]
            prod = data["products"][sel_key]
            
            st.info(f"📋 Справочно из базы данных — Стандартная розничная цена: **{prod['price']} руб.** | Остаток: **{prod['qty']} шт.**")
            
            # Форма оформления продажи
            with st.form("sale_form"):
                sqty = st.number_input("Количество для продажи (шт)", min_value=1, max_value=int(prod["qty"]), value=1)
                
                # НОВОЕ: Возможность вписать индивидуальную цену продажи вручную
                custom_price = st.number_input("💰 Фактическая цена продажи за 1 шт (можно изменить)", min_value=0.0, value=float(prod['price']))
                
                # НОВОЕ: Выбор типа оплаты
                pay_method = st.radio("💳 Способ оплаты", ["Наличные", "Рассрочка"], horizontal=True)
                
                btn_sell = st.form_submit_button("💵 Подтвердить и продать", type="primary")
                
                if btn_sell:
                    data["products"][sel_key]["qty"] -= sqty
                    t_sale = sqty * custom_price
                    t_cost = sqty * prod["cost"]  # Себестоимость берется фиксированная из базы
                    
                    data["sales"].append({
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "day": datetime.now().strftime("%Y-%m-%d"),
                        "name": sel_display, 
                        "qty": sqty,
                        "total_sale": t_sale, 
                        "total_cost": t_cost, 
                        "profit": t_sale - t_cost,
                        "payment": pay_method  # Сохраняем тип оплаты
                    })
                    save_data(data)
                    st.success(f"Продано! Товар: {sel_display} ({sqty} шт.) на сумму {t_sale} руб. Метод: {pay_method}")
                    st.rerun()

# --- ВКЛАДКА 3: ОТЧЕТЫ С ТИПОМ ОПЛАТЫ ---
elif menu == "📊 Отчеты по дням":
    st.header("Аналитика и история продаж")
    if not data["sales"]:
        st.write("Продаж еще не было.")
    else:
        df = pd.DataFrame(data["sales"])
        df['day'] = pd.to_datetime(df['day']).dt.date
        
        st.subheader("🔍 Выберите период для просмотра отчета")
        today = datetime.now().date()
        date_range = st.date_input("Диапазон дат", value=(today, today))
        
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[(df['day'] >= start_date) & (df['day'] <= end_date)]
        else:
            filtered_df = df
            
        if filtered_df.empty:
            st.info("За выбранный период продаж не найдено.")
        else:
            c1, c2 = st.columns(2)
            c1.metric("💰 Выручка за период", f"{filtered_df['total_sale'].sum():,.2f} руб.")
            c2.metric("📈 Чистая прибыль за период", f"{filtered_df['profit'].sum():,.2f} руб.")
            
            # Дополнительное отображение по типам оплаты, если колонка существует
            if "payment" in filtered_df.columns:
                st.subheader("💳 Разделение по типам оплаты за период")
                p1, p2 = st.columns(2)
                cash_sum = filtered_df[filtered_df['payment'] == 'Наличные']['total_sale'].sum()
                credit_sum = filtered_df[filtered_df['payment'] == 'Рассрочка']['total_sale'].sum()
                p1.metric("💵 Наличными", f"{cash_sum:,.2f} руб.")
                p2.metric("📝 В рассрочку", f"{credit_sum:,.2f} руб.")
            
            st.subheader("📋 Детальный список проданных товаров")
            
            # Переименовываем колонки для красивого вывода
            rename_dict = {
                "date": "Дата/Время", "day": "Дата", "name": "Товар", 
                "qty": "Кол-во (шт)", "total_sale": "Сумма продажи", 
                "total_cost": "Себестоимость", "profit": "Прибыль"
            }
            if "payment" in filtered_df.columns:
                rename_dict["payment"] = "Тип оплаты"
                
            display_df = filtered_df.rename(columns=rename_dict)
            st.dataframe(display_df.sort_values(by="Дата/Время", ascending=False), use_container_width=True)
