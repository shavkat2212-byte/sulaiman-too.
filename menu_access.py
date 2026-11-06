# Права доступа к пунктам главного меню по роли
# Версия: 1.0

ALL_MENU_OPTIONS = [
    "🛒 Продажи",
    "📦 Склад",
    "📋 Инвентаризация",
    "📤 Архив",
    "👥 Клиенты",
    "📱 Выписка клиента",
    "🛠️ Правка рассрочек",
    "💵 Касса",
    "📊 Отчеты",
    "🤝 Долг с поставщиком",
]

# Скрыты у всех, кроме администратора
ADMIN_ONLY_MENU = (
    "📤 Архив",
    "🛠️ Правка рассрочек",
    "📦 Склад",
    "💵 Касса",
    "🤝 Долг с поставщиком",
)

DEFAULT_MENU = "🛒 Продажи"


def menu_options_for_role(role: str) -> list:
    """Список пунктов бокового меню для роли. Поставщик сюда не ходит."""
    if role == "Администратор":
        return list(ALL_MENU_OPTIONS)
    # Кассир (и любой не-админ в этом меню): без склада, кассы, долга, архива, правки рассрочек
    return [item for item in ALL_MENU_OPTIONS if item not in ADMIN_ONLY_MENU]


def can_open_menu(role: str, choice: str) -> bool:
    """Можно ли открыть раздел choice в роли role (для диспетчера)."""
    if not choice:
        return False
    return choice in menu_options_for_role(role)


def sanitize_menu_choice(role: str, choice: str | None) -> str:
    """Сброс устаревшего выбора сессии на допустимый пункт."""
    if choice and can_open_menu(role, choice):
        return choice
    return DEFAULT_MENU
