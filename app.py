# Магазин «Сулайман-Тоо» — Главный модуль: Маршрутизация (Без авторизации)
# Версия программы: 1.4.5 (Полный откат к открытому доступу)

import streamlit as st

# Импорты модулей
from stock import show_stock_page
from sales import show_sales_page
from clients import show_clients_page
try: from cash import show_cash_page
except: show_cash_page = lambda: st.title("💵 Касса (Модуль в разработке)")
try: from reports import show_reports_page
except: show_reports_page = lambda: st.title("📊 Отчеты")

st.set_page_config(page_title="Магазин «Сулайман-Тоо»", page_icon="🛍️", layout="wide")

# Инициализация корзины
if "cart" not in st.session_state:
    st.session_state.cart = []

st.sidebar.markdown("### 🛠️ Главное меню")

# Твои новые переименованные разделы (открыты для всех)
menu_options = [
    "📦 Склад", 
    "🛒 Продажи", 
    "👥 Клиенты", 
    "💵 Касса", 
    "📊 Отчеты"
]

choice = st.sidebar.radio("Перейти в раздел:", menu_options)

st.sidebar.markdown("---")
st.sidebar.caption("Магазин «Сулайман-Тоо» v1.4.5")

if choice == "📦 Склад":
    show_stock_page()
elif choice == "🛒 Продажи":
    show_sales_page()
elif choice == "👥 Клиенты":
    show_clients_page()
elif choice == "💵 Касса":
    show_cash_page()
elif choice == "📊 Отчеты":
    show_reports_page()
