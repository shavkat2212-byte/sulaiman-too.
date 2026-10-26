# Магазин «Сулайман-Тоо» — Главный модуль: Авторизация и Маршрутизация
# Версия программы: 1.17.0 (кассир на складе меняет только название; долг с поставщиком; вход по логину с «Запомнить меня»)

import streamlit as st
from utils import (
    format_date_to_ddmmyyyy,
    fix_legacy_zero_month,
    fix_contract_name_on_fly,
    get_batch_display_date
)
from database import (authenticate_user, check_has_users, hash_password, supabase, clear_data_cache,
                      create_session_token, user_from_session_token, delete_session_token)
from supplier_logic import SUPPLIER_ROLE
from supplier_debt import show_supplier_debt_page

from stock import show_stock_page
from sales import show_sales_page
from clients import show_clients_page
try:
    from inventory import show_inventory_page
except Exception:
    show_inventory_page = lambda: st.title("Инвентаризация недоступна")
try:
    from shop_tools import show_archive_page
except Exception:
    show_archive_page = lambda: st.title("Архив недоступен")
try:
    from statement import show_statement_page
except Exception:
    show_statement_page = lambda: st.title("Выписка клиента недоступна")
try:
    from installment_admin import show_installment_admin_page
except Exception:
    show_installment_admin_page = lambda: st.title("Правка рассрочек недоступна")
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

if st.session_state.get("user") is None and st.query_params.get("s"):
    remembered = user_from_session_token(st.query_params.get("s"))
    if remembered:
        st.session_state.user = remembered
    else:
        del st.query_params["s"]

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

def _logout():
    token = st.query_params.get("s")
    if token:
        delete_session_token(token)
        del st.query_params["s"]
    st.session_state.user = None
    st.session_state.pop("menu_choice", None)
    st.rerun()


if user_role == SUPPLIER_ROLE:
    # Поставщик видит только свой блок долга — ни кассы, ни склада, ни клиентов
    if st.sidebar.button("🚪 Выйти", width="stretch"):
        _logout()
    st.sidebar.caption("Магазин «Сулайман-Тоо» v1.17.0")
    show_supplier_debt_page()
    st.stop()

if user_role == "Администратор":
    if st.sidebar.button("🚪 Выйти в режим Кассира", width="stretch"):
        _logout()
else:
    st.sidebar.markdown("---")
    with st.sidebar.expander("🔐 Войти как Администратор"):
        with st.form("admin_password_only_form"):
            input_pass = st.text_input("Введите пароль администратора", type="password")
            if st.form_submit_button("Подтвердить вход", width="stretch"):
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
    with st.sidebar.expander("🔑 Вход по логину (поставщик)"):
        with st.form("login_form"):
            in_user = st.text_input("Логин")
            in_pass = st.text_input("Пароль", type="password")
            remember = st.checkbox("Запомнить меня", value=True)
            if st.form_submit_button("Войти", width="stretch"):
                found = authenticate_user(in_user, in_pass) if in_user and in_pass else None
                if found:
                    st.session_state.user = found
                    if remember:
                        token = create_session_token(found["id"])
                        if token:
                            st.query_params["s"] = token
                    st.rerun()
                else:
                    st.error("❌ Неверный логин или пароль")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Главное меню")

menu_options = ["🛒 Продажи", "📦 Склад", "📋 Инвентаризация", "📤 Архив", "👥 Клиенты", "📱 Выписка клиента", "🛠️ Правка рассрочек", "💵 Касса", "📊 Отчеты", "🤝 Долг с поставщиком"]
if user_role != "Администратор":
    menu_options = [item for item in menu_options if item not in ("📤 Архив", "🛠️ Правка рассрочек")]
if "menu_choice" not in st.session_state or st.session_state.menu_choice not in menu_options:
    st.session_state.menu_choice = "🛒 Продажи"

choice = st.sidebar.radio(
    "Перейти в раздел:",
    menu_options,
    index=menu_options.index(st.session_state.menu_choice),
    key="menu_radio"
)
st.session_state.menu_choice = choice

if choice == "👥 Клиенты" and st.session_state.get("_last_menu") != "👥 Клиенты":
    for k in ("credit_client_pick", "credit_sale_pick", "credit_pay_pick", "credit_bound_client", "_clients_entry"):
        st.session_state.pop(k, None)
st.session_state["_last_menu"] = choice

if st.sidebar.button("🔄 Обновить данные", width="stretch"):
    clear_data_cache()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Магазин «Сулайман-Тоо» v1.17.0")

if choice == "📦 Склад":
    show_stock_page()
elif choice == "📋 Инвентаризация":
    show_inventory_page()
elif choice == "📤 Архив":
    show_archive_page()
elif choice == "🛒 Продажи":
    show_sales_page()
elif choice == "👥 Клиенты":
    show_clients_page()
elif choice == "📱 Выписка клиента":
    show_statement_page()
elif choice == "🛠️ Правка рассрочек":
    show_installment_admin_page()
elif choice == "💵 Касса":
    show_cash_page()
elif choice == "📊 Отчеты":
    show_reports_page()
elif choice == "🤝 Долг с поставщиком":
    show_supplier_debt_page()
