# Магазин «Сулайман-Тоо» — Главный модуль: Авторизация и Маршрутизация
# Версия программы: 1.6.1 (Откат к стабильной сессии без внешних зависимостей)

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

# Инициализация состояния авторизации (встроенная память Streamlit)
if "user" not in st.session_state:
    st.session_state.user = None

# --- Окно авторизации ---
if st.session_state.user is None:
    st.title("🛍️ Автоматизированная система «Сулайман-Тоо»")
    
    if not check_has_users():
        st.warning("⚠️ В системе не зарегистрировано ни одного пользователя. Создайте первого Администратора:")
        with st.form("first_run_form"):
            new_login = st.text_input("Логин администратора")
            new_pass = st.text_input("Пароль администратора", type="password")
            if st.form_submit_button("Создать администратора и войти"):
                if new_login and new_pass:
                    if create_new_user(new_login, new_pass, "Администратор"):
                        st.success("Администратор успешно создан! Теперь войдите в систему.")
                        st.rerun()
                    else:
                        st.error("Не удалось создать пользователя.")
                else:
                    st.error("Заполните все поля!")
        st.stop()

    st.subheader("🔐 Вход в систему")
    with st.form("login_form"):
        username_input = st.text_input("Имя пользователя (Логин)")
        password_input = st.text_input("Пароль", type="password")
        submit_login = st.form_submit_button("Войти")
        
        if submit_login:
            user_data = authenticate_user(username_input, password_input)
            if user_data:
                st.session_state.user = user_data
                st.success(f"Добро пожаловать, {user_data['username']}!")
                st.rerun()
            else:
                st.error("❌ Неверный логин или пароль")
    st.stop()

# --- Раздел, если пользователь уже авторизован ---
current_user = st.session_state.user
user_role = current_user["role"]

st.sidebar.markdown(f"### 👤 {current_user['username']}")
st.sidebar.info(f"Роль: **{user_role}**")

if st.sidebar.button("🚪 Выйти из аккаунта", use_container_width=True):
    st.session_state.user = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Главное меню")

# Все пункты меню доступны обоим, ограничения настроены внутри модулей
menu_options = ["📦 Склад", "🛒 Продажи", "👥 Клиенты", "💵 Касса", "📊 Отчеты"]
choice = st.sidebar.radio("Перейти в раздел:", menu_options)

# Панель управления пользователями доступна ТОЛЬКО Администратору
if user_role == "Администратор":
    st.sidebar.markdown("---")
    with st.sidebar.expander("➕ Создать пользователя"):
        with st.form("create_user_sidebar"):
            u_name = st.text_input("Логин")
            u_pass = st.text_input("Пароль", type="password")
            u_role = st.selectbox("Роль", ["Кассир", "Администратор"])
            if st.form_submit_button("Зарегистрировать"):
                if u_name and u_pass:
                    if create_new_user(u_name, u_pass, u_role):
                        st.success(f"Пользователь {u_name} создан!")
                    else:
                        st.error("Ошибка (возможно логин занят)")
                else:
                    st.error("Заполните поля")

st.sidebar.markdown("---")
st.sidebar.caption("Магазин «Сулайман-Тоо» v1.6.1")

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
