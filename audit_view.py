# Магазин «Сулайман-Тоо» — Журнал изменений (audit_log): разбор и фильтры
# Версия: 1.0
# Чистые функции без Streamlit и без базы — экран в cash.py.

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Bishkek")
except Exception:  # pragma: no cover
    LOCAL_TZ = timezone(timedelta(hours=6))

ACTION_LABELS = {
    "CREATE": "Создание",
    "UPDATE": "Изменение",
    "DELETE": "Удаление",
    "PAYMENT_ANNUL": "Аннулирование оплаты",
    "SCHEDULE_UPDATE": "График: изменение платежа",
    "SCHEDULE_INSERT": "График: новый платёж",
    "SCHEDULE_DELETE": "График: удаление платежа",
    "CONTRACT_UPDATE": "Договор: сумма рассрочки",
}
TABLE_LABELS = {
    "cash_operations": "Касса",
    "credit_payments": "График платежей",
    "sales": "Договоры",
}
FIELD_LABELS = {
    "amount": "сумма",
    "comment": "комментарий",
    "date": "дата",
    "amount_paid": "оплачено",
    "amount_expected": "ожидается",
    "due_date": "дата платежа",
    "status": "статус",
    "credit_balance": "сумма рассрочки",
    "cash_operation_id": "касса №",
    "sale_id": "договор",
}
SKIP_FIELDS = {"at", "client_id"}


def entry_time(entry):
    """Время записи в часовом поясе Бишкека (created_at из базы в UTC; запасной вариант — new_data.at)."""
    raw = entry.get("created_at")
    if raw:
        text = str(raw).replace("Z", "+00:00").replace(" ", "T", 1)
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(LOCAL_TZ).replace(tzinfo=None)
        except ValueError:
            pass
    at = (entry.get("new_data") or {}).get("at") if isinstance(entry.get("new_data"), dict) else None
    if at:
        try:
            return datetime.strptime(str(at)[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return None


def fmt_value(v):
    if isinstance(v, float) and v == int(v):
        v = int(v)
    if isinstance(v, (int, float)):
        return f"{v:,}".replace(",", " ")
    return str(v)


def describe(data):
    if not data:
        return ""
    if not isinstance(data, dict):
        return str(data)
    parts = []
    for k, v in data.items():
        if k in SKIP_FIELDS or v is None:
            continue
        parts.append(f"{FIELD_LABELS.get(k, k)}: {fmt_value(v)}")
    return "; ".join(parts)


def journal_rows(entries):
    rows = []
    for e in entries:
        when = entry_time(e)
        rows.append({
            "when": when,
            "Когда": when.strftime("%d.%m.%Y %H:%M") if when else "—",
            "Кто": e.get("user_name") or "—",
            "Раздел": TABLE_LABELS.get(e.get("table_name"), e.get("table_name") or "—"),
            "Действие": ACTION_LABELS.get(e.get("action"), e.get("action") or "—"),
            "ID": str(e.get("record_id") or ""),
            "Было": describe(e.get("old_data")),
            "Стало": describe(e.get("new_data")),
            "Комментарий": e.get("comment") or "",
        })
    rows.sort(key=lambda r: r["when"] or datetime.min, reverse=True)
    return rows


def filter_rows(rows, date_from=None, date_to=None, sections=None, actions=None, user=None, text=None):
    out = []
    q = (text or "").strip().lower()
    for r in rows:
        d = r["when"].date() if r["when"] else None
        if date_from and (d is None or d < date_from):
            continue
        if date_to and (d is None or d > date_to):
            continue
        if sections and r["Раздел"] not in sections:
            continue
        if actions and r["Действие"] not in actions:
            continue
        if user and user != "Все" and r["Кто"] != user:
            continue
        if q and q not in " ".join(str(r[k]) for k in ("ID", "Было", "Стало", "Комментарий", "Кто")).lower():
            continue
        out.append(r)
    return out
