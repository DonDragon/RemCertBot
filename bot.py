
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import BOT_TOKEN
from db import (
    init_db, insert_certificate, grant_access, revoke_access,
    get_shared_with, has_view_access, get_certificates_for_user, get_certificates_shared_with
)
from cert_parser import parse_certificate
from utils import extract_zip, is_certificate_file
import os
import tempfile
import sqlite3
from datetime import datetime

init_db()

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            ["📥 Загрузить сертификат", "📄 Мои сертификаты"],
            ["🔍 Поиск по фирме", "👁 Доступы"]
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
    await update.message.reply_text("👋 Привет! Я RemCertBot. Выберите действие:", reply_markup=main_menu_keyboard())

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if text == "📥 Загрузить сертификат":
        await update.message.reply_text("📎 Просто отправьте файл сертификата или архив .zip.")
    elif text == "📄 Мои сертификаты":
        await certs_cmd(update, context)
    elif text == "🔍 Поиск по фирме":
        await update.message.reply_text("🔎 Используйте команду: /firm <название>")
    elif text == "👁 Доступы":
        await update.message.reply_text("🔐 Управление доступом:", reply_markup=access_menu_keyboard())

async def share_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❗ Использование: /share <user_id>")
        return
    try:
        viewer_id = int(context.args[0])
        grant_access(owner_id, viewer_id)
        await update.message.reply_text(f"✅ Доступ открыт пользователю {viewer_id}.")
    except:
        await update.message.reply_text("❌ Неверный ID.")

async def unshare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❗ Использование: /unshare <user_id>")
        return
    try:
        viewer_id = int(context.args[0])
        revoke_access(owner_id, viewer_id)
        await update.message.reply_text(f"🚫 Доступ для {viewer_id} удалён.")
    except:
        await update.message.reply_text("❌ Неверный ID.")

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

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("certs", certs_cmd))
    app.add_handler(CommandHandler("share", share_cmd))
    app.add_handler(CommandHandler("unshare", unshare_cmd))
    app.add_handler(CommandHandler("shared", shared_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
