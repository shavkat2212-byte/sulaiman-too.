# utils.py
# Вспомогательные функции для работы с датами и договорами
# Версия: 1.0

from datetime import datetime, timedelta
import re

def format_date_to_ddmmyyyy(date_str: str, include_time: bool = False) -> str:
    """
    Универсальное форматирование даты в DD.MM.YYYY
    Поддерживает входные форматы: YYYY-MM-DD, DD.MM.YYYY, с временем и без.
    """
    if not date_str:
        return "-"
    
    date_str = str(date_str).strip()
    
    # Если уже в формате DD.MM.YYYY — возвращаем как есть
    if "." in date_str[:10]:
        if include_time and " " in date_str:
            return date_str
        return date_str.split()[0] if not include_time else date_str
    
    try:
        if " " in date_str:
            date_part, time_part = date_str.split(" ", 1)
            parsed = datetime.strptime(date_part, "%Y-%m-%d")
            formatted = parsed.strftime("%d.%m.%Y")
            return f"{formatted} {time_part}" if include_time else formatted
        else:
            parsed = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return parsed.strftime("%d.%m.%Y")
    except Exception:
        return date_str


def fix_legacy_zero_month(date_str: str) -> str:
    """
    Исправляет старые записи с битой датой вида 05.00.2026
    Заменяет .00. на текущий месяц.
    """
    if not date_str:
        return date_str
    date_str = str(date_str)
    if ".00." in date_str:
        current_month = datetime.now().strftime("%m")
        return date_str.replace(".00.", f".{current_month}.")
    return date_str


def fix_contract_name_on_fly(name_str: str, date_str: str) -> str:
    """
    Исправляет старые номера договоров вида №202607 на правильный номер по дате.
    """
    if not name_str:
        return name_str
    name_str = str(name_str)
    if "№202607" in name_str:
        clean_date = format_date_to_ddmmyyyy(date_str, include_time=False)
        new_num = clean_date.replace(".", "")[:4]
        return name_str.replace("№202607", f"№{new_num}")
    return name_str


def parse_date_flexible(date_str: str):
    """Пытается распарсить дату в разных форматах. Возвращает datetime или None."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    
    formats = [
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:19] if len(date_str) > 19 else date_str, fmt)
        except ValueError:
            continue
    return None


def get_batch_display_date(date_str: str) -> str:
    """Форматирует дату партии для отображения в выпадающих списках."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')
    except Exception:
        return date_str


def add_months(date_obj, months: int):
    """Добавляет N месяцев к дате (для расчёта рассрочки)."""
    for _ in range(months):
        month = date_obj.month
        year = date_obj.year + (month + 1 - 1) // 12
        month = (month + 1 - 1) % 12 + 1
        date_obj = date_obj.replace(year=year, month=month)
    return date_obj
