# Магазин «Сулайман-Тоо» — Главный модуль: Маршрутизация и Авторизация
# Версия программы: 1.4 (Внедрено окно авторизации сотрудников и переименовано меню)

import streamlit as st
from database import supabase

# Импорты модулей
from stock import show_stock_page
from sales import show_sales_page
from clients import show_clients_page
try: from cash import show_cash_page
except: show_cash_page = lambda: st.title("💵 Касса (Модуль в разработке)")
try: from reports import show_reports_page
except: show_reports_page = lambda: st.title("📊 Отчеты (Модуль в разработке)")

st.set_page_config(page_title="Магазин «Сулайман-Тоо»", page_icon="🛍️", layout="wide")

# Инициализация состояний сессии
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "user_fio" not in st.session_state:
    st.session_state.user_fio = ""
if "cart" not in st.session_state:
    st.session_state.cart = []

# =========================================================================
# ОКНО ВХОДА В СИСТЕМУ
# =========================================================================
if not st.session_state.authenticated:
    st.markdown("<h2 style='text-align: center;'>🔐 Вход в систему «Сулайман-Тоо»</h2>", unsafe_style_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        with st.form("login_form"):
            username_input = st.text_input("👤 Логин пользователя").strip()
            password_input = st.text_input("🔑 Пароль", type="password").strip()
            submit_login = st.form_submit_button("Войти в систему", use_container_width=True)
            
            if submit_login:
                if username_input and password_input:
                    try:
                        # Проверяем сотрудника в базе Supabase
                        res = supabase.table("employees").select("*").eq("username", username_input).eq("password", password_input).execute()
                        if res.data:
                            user = res.data[0]
                            st.session_state.authenticated = True
                            st.session_state.user_role = user["role"]
                            st.session_state.user_fio = user["fio"]
                            st.success(f"Добро пожаловать, {user['fio']}!")
                            st.rerun()
                        else:
                            st.error("❌ Неверный логин или пароль!")
                    except Exception as e:
                        st.error(f"Ошибка подключения к базе: {e}")
                else:
                    st.warning("Заполните все поля для входа!")
    st.stop()

# =========================================================================
# ОСНОВНОЙ ИНТЕРФЕЙС ПРОГРАММЫ (ДЛЯ АВТОРИЗОВАННЫХ ПОЛЬЗОВАТЕЛЕЙ)
# =========================================================================

st.sidebar.markdown(f"👤 **Сотрудник:**\n{st.session_state.user_fio}")
st.sidebar.markdown(f"🔑 **Роль:** `{st.session_state.user_role}`")
if st.sidebar.button("🚪 Выйти из аккаунта", use_container_width=True):
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.session_state.user_fio = ""
    st.session_state.cart = []
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Главное меню")

# Твои новые переименованные разделы
menu_options = ["📦 Склад", "🛒 Продажи", "👥 Клиенты"]

# Добавляем скрытые разделы ТОЛЬКО если вошел Администратор
if st.session_state.user_role == "Администратор":
    menu_options.append("💵 Касса")
    menu_options.append("📊 Отчеты")

choice = st.sidebar.radio("Перейти в раздел:", menu_options)

st.sidebar.markdown("---")
st.sidebar.caption("Магазин «Сулайман-Тоо» v1.4")

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
