# Магазин «Сулайман-Тоо» — Главный модуль: Авторизация и Маршрутизация
# Версия программы: 1.7.5 (Исправлен двойной вход, авторизация только по паролю админа)

import streamlit as st
from database import authenticate_user, check_has_users, hash_password, supabase

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

# Автоматический быстрый вход для Кассира при старте
if "user" not in st.session_state or st.session_state.user is None:
    st.session_state.user = {
        "id": 0,
        "username": "Кассир (Быстрый доступ)",
        "role": "Кассир"
    }

current_user = st.session_state.user
user_role = current_user["role"]

# --- БОКОВАЯ ПАНЕЛЬ ---
st.sidebar.markdown(f"### 👤 {current_user['username']}")
st.sidebar.info(f"Текущий режим: **{user_role}**")

# Кнопка переключения режимов
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
                    # Ищем в базе пользователя с ролью Администратор и таким хэшем
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

menu_options = ["📦 Склад", "🛒 Продажи", "👥 Клиенты", "💵 Касса", "📊 Отчеты"]
choice = st.sidebar.radio("Перейти в раздел:", menu_options)

st.sidebar.markdown("---")
st.sidebar.caption("Магазин «Сулайман-Тоо» v1.7.5")

# Роутинг страниц
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
