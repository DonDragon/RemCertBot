from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import BOT_TOKEN
from db import (
    init_db, insert_certificate, grant_access, revoke_access,
    get_shared_with, has_view_access,
    get_certificates_for_user, get_certificates_shared_with,
    get_user_language, set_user_language
)
from cert_parser import parse_certificate
from utils import extract_zip, is_certificate_file
from i18n import translations
import os
import tempfile
from datetime import datetime

init_db()

def _(key, lang="ua"):
    return translations.get(lang, translations["ua"]).get(key, key)

def build_main_menu(lang="ua"):
    return ReplyKeyboardMarkup(
        keyboard=[
            [_(key="menu_upload", lang=lang), _(key="menu_my", lang=lang)],
            [_(key="menu_search", lang=lang), _(key="menu_access", lang=lang)]
        ],
        resize_keyboard=True
    )

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from db import get_user_language, set_user_language
    from i18n import translations

    def _(key, lang="ua"):
        return translations.get(lang, translations["ua"]).get(key, key)

    tg_lang = update.effective_user.language_code or "ua"
    known_langs = ["ua", "ru", "en"]

    # если пользователь не в базе или установлен дефолт — устанавливаем язык Telegram
    if get_user_language(user_id) == "ua" and tg_lang in known_langs:
        set_user_language(user_id, tg_lang)

    lang = get_user_language(user_id)
    from bot import build_main_menu
    await update.message.reply_text(_(key="welcome", lang=lang), reply_markup=build_main_menu(lang))


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    document = update.message.document

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, document.file_name)
        tg_file = await document.get_file()
        await tg_file.download_to_drive(file_path)

        cert_paths = []
        if document.file_name.lower().endswith(".zip"):
            extract_zip(file_path, tmpdir)
            for root, _, files in os.walk(tmpdir):
                for name in files:
                    if is_certificate_file(name):
                        cert_paths.append(os.path.join(root, name))
        elif is_certificate_file(document.file_name):
            cert_paths.append(file_path)
        else:
            await update.message.reply_text("❌ Unsupported file format.")
            return

        added = 0
        skipped = 0
        for cert_path in cert_paths:
            try:
                cert = parse_certificate(cert_path)
                filename = os.path.basename(cert_path)
                if insert_certificate(cert, user_id, filename):
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка: {e}")
        await update.message.reply_text(f"✅ Добавлено: {added}, Пропущено: {skipped}")

async def certs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    own = get_certificates_for_user(user_id)
    shared = get_certificates_shared_with(user_id)

    if not own and not shared:
        await update.message.reply_text(_(key="no_certificates", lang=lang))
        return

    lines = [f"📄 {_(key='menu_my', lang=lang)}:"]
    idx = 1

    if own:
        lines.append(f" 🗂 *{_(key='own_certs', lang=lang)}*:")
        for org, director, valid_to in own:
            valid_date = datetime.fromisoformat(valid_to).strftime("%d.%m.%Y")
            lines.append( f"{idx}. *{org}* 👤 {director} ⏳ До: {valid_date}")
            idx += 1

    if shared:
        lines.append(f"🔗 *{_(key='shared_certs', lang=lang)}*:")
        for org, director, valid_to in shared:
            valid_date = datetime.fromisoformat(valid_to).strftime("%d.%m.%Y")
            lines.append( f"{idx}. *{org}* 👤 {director} ⏳ До: {valid_date}")
            idx += 1

    await update.message.reply_text("".join(lines), parse_mode="Markdown")

async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    if text == _(key="menu_upload", lang=lang):
        await update.message.reply_text("📎 Просто отправьте файл сертификата или архив .zip.")
    elif text == _(key="menu_my", lang=lang):
        await certs_cmd(update, context)
    elif text == _(key="menu_search", lang=lang):
        await update.message.reply_text("🔎 Используйте команду: /firm <название>")
    elif text == _(key="menu_access", lang=lang):
        await update.message.reply_text("🔐 Управление доступом:", reply_markup=access_menu_keyboard())

async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    buttons = [
        [
            InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_ua"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ]
    await update.message.reply_text(_(key="choose_lang", lang=lang), reply_markup=InlineKeyboardMarkup(buttons))

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

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("certs", certs_cmd))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_lang_choice, pattern="^lang_"))
    app.run_polling()

if __name__ == "__main__":
    main()
