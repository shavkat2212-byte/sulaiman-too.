import streamlit as st
import hashlib
from supabase import create_client, Client

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Ошибка подключения к Supabase. Проверьте Secrets! {e}")
    st.stop()

def hash_password(password: str) -> str:
    """Хэширование пароля в SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def authenticate_user(username: str, password: str):
    """
    Проверяет логин и пароль в таблице users.
    Возвращает словарь с данными пользователя или None.
    """
    try:
        hashed = hash_password(password)
        response = (
            supabase.table("users")
            .select("id, username, role")
            .eq("username", username.strip())
            .eq("password_hash", hashed)
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"Ошибка при авторизации через БД: {e}")
        return None

def create_new_user(username: str, password: str, role: str) -> bool:
    """Создает нового пользователя (Администратор или Кассир)."""
    try:
        hashed = hash_password(password)
        data = {
            "username": username.strip(),
            "password_hash": hashed,
            "role": role
        }
        response = supabase.table("users").insert(data).execute()
        return bool(response.data and len(response.data) > 0)
    except Exception as e:
        st.error(f"Ошибка при создании пользователя в БД: {e}")
        return False

def check_has_users() -> bool:
    """Проверяет, есть ли вообще пользователи в таблице."""
    try:
        response = supabase.table("users").select("id", count="exact").limit(1).execute()
        # Возвращает True, если в таблице есть хотя бы одна запись
        return bool(response.data and len(response.data) > 0)
    except:
        return False
