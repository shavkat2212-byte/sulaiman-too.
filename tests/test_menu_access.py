# Меню по ролям: python -m pytest tests/test_menu_access.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from menu_access import (  # noqa: E402
    ALL_MENU_OPTIONS,
    ADMIN_ONLY_MENU,
    DEFAULT_MENU,
    menu_options_for_role,
    can_open_menu,
    sanitize_menu_choice,
)

HIDDEN_FOR_CASHIER = ("📦 Склад", "💵 Касса", "🤝 Долг с поставщиком", "📤 Архив", "🛠️ Правка рассрочек")
VISIBLE_FOR_CASHIER = ("🛒 Продажи", "📋 Инвентаризация", "👥 Клиенты", "📱 Выписка клиента", "📊 Отчеты")


def test_admin_sees_all():
    opts = menu_options_for_role("Администратор")
    assert opts == ALL_MENU_OPTIONS
    for item in ALL_MENU_OPTIONS:
        assert can_open_menu("Администратор", item)


def test_cashier_hides_stock_cash_supplier_debt():
    opts = menu_options_for_role("Кассир")
    for item in HIDDEN_FOR_CASHIER:
        assert item not in opts
        assert not can_open_menu("Кассир", item)
    for item in VISIBLE_FOR_CASHIER:
        assert item in opts
        assert can_open_menu("Кассир", item)
    # Не скрываем лишнее
    assert "📋 Инвентаризация" in opts
    assert "📊 Отчеты" in opts


def test_stale_menu_choice_reset():
    assert sanitize_menu_choice("Кассир", "💵 Касса") == DEFAULT_MENU
    assert sanitize_menu_choice("Кассир", "📦 Склад") == DEFAULT_MENU
    assert sanitize_menu_choice("Кассир", "🤝 Долг с поставщиком") == DEFAULT_MENU
    assert sanitize_menu_choice("Кассир", None) == DEFAULT_MENU
    assert sanitize_menu_choice("Кассир", "🛒 Продажи") == "🛒 Продажи"
    assert sanitize_menu_choice("Администратор", "💵 Касса") == "💵 Касса"


def test_admin_only_set_matches_hidden():
    assert set(HIDDEN_FOR_CASHIER) == set(ADMIN_ONLY_MENU)
