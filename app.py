# Магазин «Сулайман-Тоо» — Главный модуль: Авторизация и Маршрутизация
# Версия программы: 1.7.0 (Гостевой вход для Кассира по умолчанию без пароля)

import streamlit as st
from database import authenticate_user, create_new_user, check_has_users

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

# --- АВТОМАТИЧЕСКИЙ ВХОД ДЛЯ КАССИРА ---
# Если в системе никто не авторизован, принудительно ставим роль Гостя-Кассира
if "user" not in st.session_state or st.session_state.user is None:
    st.session_state.user = {
        "id": 0,
        "username": "Кассир (Быстрый доступ)",
        "role": "Кассир"
    }

current_user = st.session_state.user
user_role = current_user["role"]

# --- БОКОВАЯ ПАНЕЛЬ И МЕНЮ ---
st.sidebar.markdown(f"### 👤 {current_user['username']}")
st.sidebar.info(f"Текущий режим: **{user_role}**")

# Кнопка переключения режимов в зависимости от того, кто залогинен
if user_role == "Администратор":
    if st.sidebar.button("🚪 Выйти в режим Кассира", use_container_width=True):
        st.session_state.user = None # Сбросит на Кассира по умолчанию
        st.rerun()
else:
    # Если зашел Кассир, внизу даем возможность Администратору войти под своим паролем
    with st.sidebar.expander("🔐 Войти как Администратор"):
        with st.form("admin_login_form", clear_on_submit=True):
            admin_pass = st.text_input("Введите пароль администратора", type="password")
            if st.form_submit_button("Подтвердить вход"):
                # Для упрощения ищем пользователя со статусом Администратор
                # Проверяем пароль через функцию authenticate_user (логин 'admin' или твой логин)
                # Чтобы не вводить логин, мы попробуем авторизовать по логину "admin" или первому попавшемуся админу.
                # Но надежнее — дать ввести логин админа:
                st.info("Введите ваш логин администратора выше (или создайте его):")

# Нам нужно, чтобы админ мог ввести свой логин и пароль в экспандере:
if user_role == "Кассир":
    st.sidebar.markdown("---")
    with st.sidebar.expander("🔐 Вход для Администратора"):
        with st.form("admin_login_direct"):
            a_login = st.text_input("Логин админа")
            a_pass = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти"):
                u_data = authenticate_user(a_login, a_pass)
                if u_data and u_data["role"] == "Администратор":
                    st.session_state.user = u_data
                    st.success("Успешный вход!")
                    st.rerun()
                else:
                    st.error("Неверный логин или пароль админа")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Главное меню")

# Все пункты меню на месте, ограничения теперь внутри cash.py и reports.py по роли
menu_options = ["📦 Склад", "🛒 Продажи", "👥 Клиенты", "💵 Касса", "📊 Отчеты"]
choice = st.sidebar.radio("Перейти в раздел:", menu_options)

# Панель управления пользователями доступна ТОЛЬКО когда включен режим Администратора
if user_role == "Администратор":
    st.sidebar.markdown("---")
    with st.sidebar.expander("➕ Создать нового Кассира/Админа"):
        with st.form("create_user_sidebar"):
            u_name = st.text_input("Логин нового пользователя")
            u_pass = st.text_input("Пароль", type="password")
            u_role = st.selectbox("Роль", ["Кассир", "Администратор"])
            if st.form_submit_button("Зарегистрировать"):
                if u_name and u_pass:
                    if create_new_user(u_name, u_pass, u_role):
                        st.success(f"Пользователь {u_name} создан!")
                    else:
                        st.error("Ошибка (логин занят)")
                else:
                    st.error("Заполните поля")

st.sidebar.markdown("---")
st.sidebar.caption("Магазин «Сулайман-Тоо» v1.7.0")

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
