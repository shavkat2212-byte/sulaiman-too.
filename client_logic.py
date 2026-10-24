# Логика клиента при оформлении рассрочки (без Streamlit и базы — тестируется отдельно).
import re


def norm_phone(phone):
    """Сравниваем по последним 9 цифрам: 0555 12-34-56, +996 555 123456 → 555123456."""
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits[-9:] if len(digits) >= 9 else digits


def norm_fio(fio):
    return " ".join(str(fio or "").replace("ё", "е").replace("Ё", "Е").lower().split())


def client_label(c):
    return f"{c.get('fio') or 'Без имени'} ({c.get('phone') or 'без телефона'})"


def find_duplicates(clients, fio, phone):
    """Клиенты с тем же телефоном или тем же ФИО."""
    f, p = norm_fio(fio), norm_phone(phone)
    out = []
    for c in clients:
        same_phone = bool(p) and len(p) >= 6 and norm_phone(c.get("phone")) == p
        same_fio = bool(f) and norm_fio(c.get("fio")) == f
        if same_phone or same_fio:
            out.append(c)
    return out


def new_client_payload(fio, phone, address, passport, comment=None, extra=None, comment_required=False):
    """Проверяет поля нового клиента. Возвращает (payload, errors, warnings).

    extra — ПИН / кем выдан / дата выдачи (если колонки есть в базе).
    comment_required — «Комментарий» обязателен (колонка comment есть в базе)."""
    fio = " ".join(str(fio or "").split())
    phone, address, passport = (str(x or "").strip() for x in (phone, address, passport))
    comment = str(comment or "").strip()
    errors, warnings = [], []
    if len(fio) < 3:
        errors.append("Укажите ФИО клиента")
    elif len(fio.split()) < 2:
        warnings.append("Укажите фамилию и имя полностью")
    if not phone:
        warnings.append("Телефон не указан — лучше указать, чтобы связаться с клиентом")
    elif len(re.sub(r"\D", "", phone)) < 9:
        warnings.append("Телефон выглядит неполным")
    pin = str((extra or {}).get("pin") or "").strip()
    if pin and len(re.sub(r"\D", "", pin)) != 14:
        warnings.append("ПИН обычно состоит из 14 цифр")
    if comment_required and not comment:
        errors.append("Заполните «Комментарий»")
    payload = {"fio": fio, "phone": phone or None, "address": address or None, "passport": passport or None}
    payload.update({k: v for k, v in (extra or {}).items()})
    if comment_required or comment:
        payload["comment"] = comment or None
    return payload, errors, warnings


def rename_contract(name, old_fio, new_fio):
    """«Договор … — Старое ФИО» → «Договор … — Новое ФИО» (если ФИО в конце названия)."""
    name = str(name or "")
    old_fio, new_fio = str(old_fio or "").strip(), str(new_fio or "").strip()
    if old_fio and new_fio and name.rstrip().endswith("— " + old_fio):
        return name.rstrip()[: -len(old_fio)] + new_fio
    return name
