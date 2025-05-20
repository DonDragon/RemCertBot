import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from notify import notify_users

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import BOT_TOKEN
from db import (
    init_db, insert_certificate, grant_access, revoke_access,
    get_shared_with, has_view_access, get_certificates_for_user, get_certificates_shared_with,
    get_user_language, set_user_language, get_all_user_ids
)

from cert_parser import parse_certificate
from utils import extract_zip, is_certificate_file
from i18n import translations
import os

def _(key, lang="ua"):
    from i18n import translations
    return translations.get(lang, translations["ua"]).get(key, key)

import tempfile
from datetime import datetime

init_db()

async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    buttons = [
        [
            InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_uk"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ]
    await update.message.reply_text(
        _(key="choose_lang", lang=lang),
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


def main_menu_keyboard(lang):
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
    tg_lang = update.effective_user.language_code or "ua"
    known_langs = ["ua", "ru", "en"]

    # Всегда записываем пользователя в базу (INSERT OR IGNORE)
    if tg_lang not in known_langs:
        tg_lang = "ua"
    set_user_language(user_id, tg_lang)

    lang = get_user_language(user_id)
    await update.message.reply_text(
        _(key="welcome", lang=lang),
        reply_markup=main_menu_keyboard(lang)
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    user_id = update.effective_user.id
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
            await update.message.reply_text("❌ Неподдерживаемый формат файла.")
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
    from db import get_certificates_for_user, get_certificates_shared_with

    own = get_certificates_for_user(user_id)
    shared = get_certificates_shared_with(user_id)

    if not own and not shared:
        await update.message.reply_text("📭 У вас нет доступных сертификатов.")
        return

    lines = ["📄 Ваши сертификаты:"]
    idx = 1

    if own:
        lines.append("\n🗂 *Собственные:*")
        for org, director, valid_to in own:
            try:
                valid_date = datetime.fromisoformat(valid_to).strftime("%d.%m.%Y")
            except:
                valid_date = valid_to
            lines.append(
                f"{idx}. *{org}*\n   👤 {director}\n   ⏳ До: {valid_date}"
            )
            idx += 1

    if shared:
        lines.append("\n🔗 *Доступные от других пользователей:*")
        for org, director, valid_to in shared:
            try:
                valid_date = datetime.fromisoformat(valid_to).strftime("%d.%m.%Y")
            except:
                valid_date = valid_to
            lines.append(
                f"{idx}. *{org}*\n   👤 {director}\n   ⏳ До: {valid_date}"
            )
            idx += 1

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lang = get_user_language(update.effective_user.id)
    if text == _(key="menu_upload", lang=lang):
        await update.message.reply_text(_(key="upload_prompt", lang=lang))
    elif text == _(key="menu_my", lang=lang):
        await certs_cmd(update, context)
    elif text == _(key="menu_search", lang=lang):
        await update.message.reply_text(_(key="send_firm", lang=lang))
    elif text == _(key="menu_access", lang=lang):
        await update.message.reply_text(_(key="access_menu", lang=lang), reply_markup=access_menu_keyboard())

async def share_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    owner_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❗ Использование: /share <user_id>")
        return
    try:
        viewer_id = int(context.args[0])
        grant_access(owner_id, viewer_id)
        await update.message.reply_text(f"{_(key='access_granted', lang=lang)} {viewer_id}.")
    except:
        await update.message.reply_text(_(key="invalid_id", lang=lang))

async def unshare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    owner_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❗ Использование: /unshare <user_id>")
        return
    try:
        viewer_id = int(context.args[0])
        revoke_access(owner_id, viewer_id)
        await update.message.reply_text(f"{_(key='access_revoked', lang=lang)} {viewer_id}.")
    except:
        await update.message.reply_text(_(key="invalid_id", lang=lang))

async def shared_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    viewers = get_shared_with(owner_id)
    if not viewers:
        await update.message.reply_text("🔒 Вы ни с кем не делитесь своими сертификатами.")
    else:
        await update.message.reply_text("📤 Ваши данные доступны: " + "\n".join(str(u) for u in viewers))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "share":
        await query.edit_message_text("✉️ Введите команду /share <user_id>, чтобы поделиться доступом.")
    elif query.data == "unshare":
        await query.edit_message_text("🧹 Введите команду /unshare <user_id>, чтобы отозвать доступ.")
    elif query.data == "shared_list":
        shared_ids = get_shared_with(user_id)
        if not shared_ids:
            await query.edit_message_text("👤 У вас нет добавленных сертификатов или доступ не передавался.")
        else:
            lines = ["🔐 Доступ открыт для:"]
            for uid in shared_ids:
                lines.append(f"• ID: `{uid}`")
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
    else:
        await query.edit_message_text("⚠️ Неизвестная команда.")

ADMIN_IDS = [127588621]  # список разрешённых ID

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет прав на эту команду.")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("❗ Используйте: /broadcast <текст>")
        return

    all_ids = get_all_user_ids()  # из базы
    count = 0
    for uid in all_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            count += 1
        except Exception:
            pass  # например, если пользователь заблокировал бота

    await update.message.reply_text(f"✅ Сообщение отправлено {count} пользователям.")


async def main():
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(notify_users, 'cron', hour=10, minute=0)
    scheduler.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("certs", certs_cmd))
    app.add_handler(CommandHandler("share", share_cmd))
    app.add_handler(CommandHandler("unshare", unshare_cmd))
    app.add_handler(CommandHandler("shared", shared_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CallbackQueryHandler(handle_lang_choice, pattern="^lang_"))
    app.add_handler(CommandHandler("broadcast", broadcast))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

