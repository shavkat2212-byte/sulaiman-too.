# Магазин «Сулайман-Тоо» — Главный модуль: Авторизация и Маршрутизация
# Версия программы: 1.7.8 (кэш данных и кнопка обновления)

import streamlit as st
from utils import (
    format_date_to_ddmmyyyy,
    fix_legacy_zero_month,
    fix_contract_name_on_fly,
    get_batch_display_date
)
from database import authenticate_user, check_has_users, hash_password, supabase, clear_data_cache

from stock import show_stock_page
from sales import show_sales_page
from clients import show_clients_page
try:
    from inventory import show_inventory_page
except Exception:
    show_inventory_page = lambda: st.title("Инвентаризация недоступна")
try:
    from cash import show_cash_page
except Exception:
    show_cash_page = lambda: st.title("💵 Касса (Модуль в разработке)")
try:
    from reports import show_reports_page
except Exception:
    show_reports_page = lambda: st.title("📊 Отчеты")

st.set_page_config(page_title="Магазин «Сулайман-Тоо»", page_icon="🛍️", layout="wide")

if "cart" not in st.session_state:
    st.session_state.cart = []

if "user" not in st.session_state or st.session_state.user is None:
    st.session_state.user = {
        "id": 0,
        "username": "Кассир (Быстрый доступ)",
        "role": "Кассир"
    }

current_user = st.session_state.user
user_role = current_user["role"]

st.sidebar.markdown(f"### 👤 {current_user['username']}")
st.sidebar.info(f"Текущий режим: **{user_role}**")

if user_role == "Администратор":
    if st.sidebar.button("🚪 Выйти в режим Кассира", use_container_width=True):
        st.session_state.user = None
        st.rerun()
else:
    st.sidebar.markdown("---")
    with st.sidebar.expander("🔐 Войти как Администратор"):
        with st.form("admin_password_only_form"):
            input_pass = st.text_input("Введите пароль администратора", type="password")
            if st.form_submit_button("Подтвердить вход", use_container_width=True):
                if input_pass:
                    hashed = hash_password(input_pass)
                    res = supabase.table("users").select("*").eq("role", "Администратор").eq("password_hash", hashed).execute()
                    if res.data and len(res.data) > 0:
                        st.session_state.user = res.data[0]
                        st.success("🔓 Доступ Администратора открыт!")
                        st.rerun()
                    else:
                        st.error("❌ Неверный пароль!")
                else:
                    st.error("Введите пароль")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Главное меню")

menu_options = ["🛒 Продажи", "📦 Склад", "📋 Инвентаризация", "👥 Клиенты", "💵 Касса", "📊 Отчеты"]
if "menu_choice" not in st.session_state or st.session_state.menu_choice not in menu_options:
    st.session_state.menu_choice = "🛒 Продажи"

choice = st.sidebar.radio(
    "Перейти в раздел:",
    menu_options,
    index=menu_options.index(st.session_state.menu_choice),
    key="menu_radio"
)
st.session_state.menu_choice = choice

if st.sidebar.button("🔄 Обновить данные", use_container_width=True):
    clear_data_cache()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Магазин «Сулайман-Тоо» v1.7.8")

if choice == "📦 Склад":
    show_stock_page()
elif choice == "📋 Инвентаризация":
    show_inventory_page()
elif choice == "🛒 Продажи":
    show_sales_page()
elif choice == "👥 Клиенты":
    show_clients_page()
elif choice == "💵 Касса":
    show_cash_page()
elif choice == "📊 Отчеты":
    show_reports_page()
