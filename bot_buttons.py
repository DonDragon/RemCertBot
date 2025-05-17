
from telegram import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# Главное меню (после /start)
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            ["📥 Загрузить сертификат", "📄 Мои сертификаты"],
            ["🔍 Поиск по фирме", "👁 Доступы"]
        ],
        resize_keyboard=True
    )

# Инлайн-кнопки управления доступом
def access_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Поделиться", callback_data="share"),
            InlineKeyboardButton("🚫 Отозвать", callback_data="unshare"),
        ],
        [
            InlineKeyboardButton("📋 Кому открыт доступ", callback_data="shared_list")
        ]
    ])
