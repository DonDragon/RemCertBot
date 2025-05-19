
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from i18n import translations

def _(key, lang="ua"):
    return translations.get(lang, translations["ua"]).get(key, key)

async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [
            InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_ua"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ]
    await update.message.reply_text(
        _(key="choose_lang", lang=get_user_language(update.effective_user.id)),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_lang_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        set_user_language(user_id, lang)
        msg = {
            "ua": "✅ Мову змінено на українську 🇺🇦",
            "ru": "✅ Язык успешно изменён на русский 🇷🇺",
            "en": "✅ Language switched to English 🇬🇧"
        }.get(lang, "✅ Language updated.")
        await query.edit_message_text(msg)
