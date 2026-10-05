import os
import time
import streamlit as st
import hashlib
from supabase import create_client, Client

def secret_value(name: str) -> str:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    if not value:
        value = os.environ.get(name)
    return value or ""

@st.cache_resource
def init_supabase() -> Client:
    url = secret_value("SUPABASE_URL")
    key = secret_value("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Нет SUPABASE_URL или SUPABASE_KEY")
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Ошибка подключения к Supabase. Проверьте Secrets! {e}")
    st.stop()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def authenticate_user(username: str, password: str):
    try:
        hashed = hash_password(password)
        response = (
            supabase.table("users")
            .select("id, username, role")
            .eq("username", username.strip())
            .eq("password_hash", hashed)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"Ошибка при авторизации через БД: {e}")
        return None

def create_new_user(username: str, password: str, role: str) -> bool:
    try:
        hashed = hash_password(password)
        data = {"username": username.strip(), "password_hash": hashed, "role": role}
        response = supabase.table("users").insert(data).execute()
        return bool(response.data)
    except Exception as e:
        st.error(f"Ошибка при создании пользователя в БД: {e}")
        return False

def check_has_users() -> bool:
    try:
        response = supabase.table("users").select("id").limit(1).execute()
        return bool(response.data)
    except Exception:
        return False

def clear_data_cache():
    st.session_state["_table_cache"] = {}

def get_rows(table_name: str, ttl: int = 40):
    cache = st.session_state.setdefault("_table_cache", {})
    now = time.time()
    item = cache.get(table_name)
    if item and now - item["ts"] < ttl:
        return item["rows"]
    rows = supabase.table(table_name).select("*").execute().data or []
    cache[table_name] = {"ts": now, "rows": rows}
    return rows
