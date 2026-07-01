import streamlit as st
from stock import show_stock_page
from sales import show_sales_page
from clients import show_clients_page
from cash import show_cash_page
from reports import show_reports_page, show_supplier_page

st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет и Рассрочки")

if "cart" not in st.session_state:
    st.session_state.cart = []

# Боковая панель меню
menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление", 
    "💰 Касса / Продажи", 
    "👥 База клиентов",
    "💵 Баланс Кассы",
    "📊 Отчеты по дням",
    "🧾 Оплата контрагентам"
])

st.sidebar.markdown("---")
st.sidebar.caption("Магазин Сулайман-Тоо • v7.0 Модульный")

# Загрузка соответствующей страницы из модулей
if menu == "📦 Склад / Поступление":
    show_stock_page()
elif menu == "💰 Касса / Продажи":
    show_sales_page()
elif menu == "👥 База клиентов":
    show_clients_page()
elif menu == "💵 Баланс Кассы":
    show_cash_page()
elif menu == "📊 Отчеты по дням":
    show_reports_page()
elif menu == "🧾 Оплата контрагентам":
    show_supplier_page()
