
import os
import tempfile
import sqlite3
from datetime import datetime
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import BOT_TOKEN
from db import init_db, insert_certificate, grant_access, revoke_access, get_shared_with, has_view_access
from cert_parser import parse_certificate
from utils import extract_zip, is_certificate_file
from bot_buttons import main_menu_keyboard, access_menu_keyboard

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я RemCertBot. Выберите действие:", reply_markup=main_menu_keyboard())

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    document: Document = update.message.document

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, document.file_name)
        tg_file = await document.get_file()
        await tg_file.download_to_drive(file_path)

        cert_paths = []
        if document.file_name.lower().endswith('.zip'):
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

        count_added = 0
        count_skipped = 0
        for cert_path in cert_paths:
            try:
                cert_info = parse_certificate(cert_path)
                filename = os.path.basename(cert_path)
                success = insert_certificate(cert_info, user_id, filename)
                if success:
                    count_added += 1
                else:
                    count_skipped += 1
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка: {e}")

        await update.message.reply_text(
            f"✅ Добавлено: {count_added}, Пропущено (дубликаты): {count_skipped}"
        )

async def certs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer_id = update.effective_user.id
    args = context.args or []
    owner_id = viewer_id

    for arg in args:
        if arg.startswith("from:"):
            try:
                owner_id = int(arg.split(":")[1])
            except:
                await update.message.reply_text("❌ Неверный формат ID.")
                return

    if owner_id != viewer_id and not has_view_access(owner_id, viewer_id):
        await update.message.reply_text("⛔ У вас нет доступа к этим сертификатам.")
        return

    sort_by = "valid_to ASC"
    if "name" in args:
        sort_by = "organization ASC"

    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute(f'''
        SELECT organization, director, valid_to
        FROM certificates
        WHERE telegram_id = ?
        ORDER BY {sort_by}
    ''', (owner_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("ℹ️ Сертификаты не найдены.")
        return

    response = "📄 Сертификаты:"

    for i, (org, director, valid_to) in enumerate(rows, 1):
        valid_dt = datetime.fromisoformat(valid_to).date()
        response += f"{i}. 🏢 {org} | 👤 {director}\n   ⏳ До: {valid_dt}\n"
    await update.message.reply_text(response)

async def firm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer_id = update.effective_user.id
    args = context.args or []
    if not args:
        await update.message.reply_text("❗ Использование: /firm <поиск> [from:<id>]")
        return

    owner_id = viewer_id
    search_terms = []

    for arg in args:
        if arg.startswith("from:"):
            try:
                owner_id = int(arg.split(":")[1])
            except:
                await update.message.reply_text("❌ Неверный формат ID.")
                return
        else:
            search_terms.append(arg)

    if owner_id != viewer_id and not has_view_access(owner_id, viewer_id):
        await update.message.reply_text("⛔ У вас нет доступа к этим сертификатам.")
        return

    search = " ".join(search_terms).lower()

    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT organization, director, inn, edrpou, valid_from, valid_to
        FROM certificates
        WHERE telegram_id = ?
        AND LOWER(organization) LIKE ?
    ''', (owner_id, f"%{search}%"))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Ничего не найдено.")
        return

    response = ""
    for org, director, inn, edrpou, valid_from, valid_to in rows:
        valid_from = datetime.fromisoformat(valid_from).date()
        valid_to = datetime.fromisoformat(valid_to).date()
        response += (
            f"🏢 {org}\n👤 {director}\n📅 {valid_from} — {valid_to}\n"
            f"🆔 ІНН: {inn} | ЄДРПОУ: {edrpou}\n\n"
        )
    await update.message.reply_text(response.strip())

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
        await update.message.reply_text("📤 Ваши данные доступны: " + "\n".join(str(uid) for uid in viewers))


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

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "share":
        await query.edit_message_text("✉️ Введите команду /share <user_id>, чтобы поделиться доступом.")
    elif query.data == "unshare":
        await query.edit_message_text("🧹 Введите команду /unshare <user_id>, чтобы отозвать доступ.")
    elif query.data == "shared_list":
        await shared_cmd(update, context)
    else:
        await query.edit_message_text("⚠️ Неизвестная команда.")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("certs", certs_cmd))
    app.add_handler(CommandHandler("firm", firm_cmd))
    app.add_handler(CommandHandler("share", share_cmd))
    app.add_handler(CommandHandler("unshare", unshare_cmd))
    app.add_handler(CommandHandler("shared", shared_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

if __name__ == "__main__":
    main()


