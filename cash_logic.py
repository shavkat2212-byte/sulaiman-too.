# Магазин «Сулайман-Тоо» — Логика кассовых операций (без Streamlit и без базы)
# Версия: 1.0
# Типы операций и правка без смены знака: приход остаётся плюсом, расход — минусом.

PREFIX_NEEDS = "[НУЖДЫ]"
PREFIX_SUPPLIER = "[ПОСТАВЩИК]"
PREFIX_ANNUL = "[АННУЛИРОВАНИЕ]"

CAT_NEEDS = "Нужды магазина"
CAT_SUPPLIER = "Оплата контрагенту"
CAT_ANNUL = "Аннулирование погашения"
CAT_NONE = "Без категории"
EXPENSE_CATS = [CAT_NEEDS, CAT_SUPPLIER, CAT_NONE]
PREFIX_BY_CAT = {CAT_NEEDS: PREFIX_NEEDS, CAT_SUPPLIER: PREFIX_SUPPLIER}


def get_category_from_comment(comment):
    comment = str(comment or "").strip()
    if comment.startswith(PREFIX_NEEDS):
        return CAT_NEEDS
    if comment.startswith(PREFIX_SUPPLIER):
        return CAT_SUPPLIER
    if comment.startswith(PREFIX_ANNUL):
        return CAT_ANNUL
    return CAT_NONE


def clean_comment(comment):
    comment = str(comment or "").strip()
    for prefix in (PREFIX_NEEDS, PREFIX_SUPPLIER, PREFIX_ANNUL):
        if comment.startswith(prefix):
            return comment[len(prefix):].strip()
    return comment


def is_annulment(op):
    return get_category_from_comment(op.get("comment")) == CAT_ANNUL


def op_kind(op):
    """'annul' — аннулирование погашения, 'income' — приход (погашение, взнос), 'expense' — расход."""
    if is_annulment(op):
        return "annul"
    return "income" if float(op.get("amount") or 0) > 0 else "expense"


def plan_cash_edit(op, new_amount_abs, new_comment, new_cat=None):
    """
    Возвращает {"amount", "comment"} для сохранения. Знак берётся из типа операции:
    приход остаётся положительным, расход — отрицательным. Аннулирования не редактируются.
    """
    kind = op_kind(op)
    if kind == "annul":
        raise ValueError("Аннулирование погашения нельзя редактировать или удалять здесь. "
                         "Исправьте график в «🛠️ Правка рассрочек» и примите оплату заново.")
    amount = abs(float(new_amount_abs or 0))
    if amount <= 0:
        raise ValueError("Сумма должна быть больше 0")
    text = str(new_comment or "").strip()
    if kind == "income":
        # у прихода нет категории-префикса: сохраняем как было, только плюсом
        return {"amount": amount, "comment": text}
    cat = new_cat if new_cat in EXPENSE_CATS else get_category_from_comment(op.get("comment"))
    prefix = PREFIX_BY_CAT.get(cat)
    return {"amount": -amount, "comment": f"{prefix} {text}".strip() if prefix else text}


def check_cash_delete(op):
    if is_annulment(op):
        raise ValueError("Аннулирование погашения удалять нельзя: касса и график разойдутся. "
                         "Если оплату нужно вернуть — примите её заново в «👥 Клиенты».")
