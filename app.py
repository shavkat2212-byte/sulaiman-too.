import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime
import io

DB_FILE = "sklad_data.json"

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("products", {})
                data.setdefault("sales", [])
                data.setdefault("cash_operations", [])
                # Миграция старых данных
                if data["products"] and not isinstance(next(iter(data["products"].values()), []), list):
                    data["products"] = {}
                return data
        except Exception:
            pass
    return {"products": {}, "sales": [], "cash_operations": []}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация
if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет")

# Sidebar
menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление", 
    "💰 Касса / Продажи", 
    "💵 Баланс Кассы",
    "📊 Отчеты по дням"
])

if st.sidebar.button("⚠️ Очистить базу данных", type="secondary"):
    if st.sidebar.checkbox("Я понимаю, что все данные будут удалены"):
        st.session_state.data = {"products": {}, "sales": [], "cash_operations": []}
        save_data(st.session_state.data)
        st.success("База очищена!")
        st.rerun()

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
def get_flat_stock():
    flat = []
    total_qty = total_cost = total_retail = 0
    for p_name, batches in data["products"].items():
        for b in batches:
            if b.get("qty", 0) > 0:
                qty = b["qty"]
                flat.append({
                    "Товар": p_name.capitalize(),
                    "Дата прихода": b["date"],
                    "Остаток": qty,
                    "Закупка": b["cost"],
                    "Продажа": b["price"],
                    "Себестоимость": qty * b["cost"]
                })
                total_qty += qty
                total_cost += qty * b["cost"]
                total_retail += qty * b["price"]
    return pd.DataFrame(flat), total_qty, total_cost, total_retail

def save_product(name: str, qty: int, cost: float, price: float, date_str: str):
    name = name.strip().lower()
    if not name:
        return False
    if name not in data["products"]:
        data["products"][name] = []
    
    for batch in data["products"][name]:
        if batch["date"] == date_str:
            batch.update({"qty": qty, "cost": cost, "price": price})
            return True
    data["products"][name].append({"date": date_str, "qty": qty, "cost": cost, "price": price})
    return True

# ====================== СКЛАД ======================
if menu == "📦 Склад / Поступление":
    st.header("Управление складом")
    
    df_stock, total_qty, total_cost, total_retail = get_flat_stock()
    
    # Метрики
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 В наличии", f"{total_qty} шт.")
    col2.metric("💰 Себестоимость", f"{total_cost:,.2f} сом")
    col3.metric("📈 Розничная стоимость", f"{total_retail:,.2f} сом")

    # Поиск
    search = st.text_input("🔍 Поиск товара", "")
    if search:
        df_stock = df_stock[df_stock["Товар"].str.contains(search, case=False)]

    print_mode = st.checkbox("🖨️ Режим для печати")

    if print_mode:
        st.subheader("ОТЧЕТ ПО ОСТАТКАМ")
        st.write(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        if not df_stock.empty:
            display_df = df_stock.copy()
            for col in ["Закупка", "Продажа", "Себестоимость"]:
                display_df[col] = display_df[col].map('{:,.2f} сом'.format)
            st.table(display_df)
        else:
            st.info("Склад пуст")
    else:
        # Импорт
        st.subheader("📥 Импорт из Excel / CSV")
        uploaded = st.file_uploader("Выберите файл", type=["xlsx", "csv"])
        if uploaded:
            try:
                if uploaded.name.endswith('.xlsx'):
                    df = pd.read_excel(uploaded)
                else:
                    df = pd.read_csv(uploaded, encoding='utf-8')
                    if df.shape[1] < 4:
                        df = pd.read_csv(uploaded, sep=None, engine='python', encoding='cp1251')
                
                count = 0
                today = datetime.now().strftime("%Y-%m-%d")
                for _, row in df.iterrows():
                    try:
                        name = str(row.iloc[0]).strip()
                        qty = int(float(str(row.iloc[1]).strip().replace(' ', '').replace(',', '.')))
                        cost = float(str(row.iloc[2]).strip().replace(' ', '').replace(',', '.'))
                        price = float(str(row.iloc[3]).strip().replace(' ', '').replace(',', '.'))
                        if save_product(name, qty, cost, price, today):
                            count += 1
                    except:
                        continue
                if count:
                    save_data(data)
                    st.success(f"✅ Импортировано {count} товаров")
                    st.rerun()
            except Exception as e:
                st.error(f"Ошибка импорта: {e}")

        # Добавление и редактирование (упрощено)
        # ... (можно оставить как было, но с вызовом save_product)

# Продолжение кода с остальными вкладками (я могу дать полностью переписанный файл)
