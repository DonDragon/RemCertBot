
import os
import tempfile
import sqlite3
from datetime import datetime
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from config import BOT_TOKEN, ADMINS
from db import init_db, insert_certificate, is_user_allowed, add_user, remove_user, list_users
from cert_parser import parse_certificate
from utils import extract_zip, is_certificate_file

# Инициализация базы
init_db()

def check_access(user_id):
    return user_id in ADMINS or is_user_allowed(user_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    await update.message.reply_text("✅ Отправьте сертификат (.cer/.pem/.crt) или архив .zip")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа к загрузке.")
        return

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
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return

    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    sort_by = context.args[0] if context.args else "date"
    if sort_by not in ["date", "name"]:
        await update.message.reply_text("❗ Использование: /certs [date|name]")
        return

    order_clause = "ORDER BY valid_to ASC" if sort_by == "date" else "ORDER BY organization ASC"
    cursor.execute(f'''
        SELECT organization, director, valid_to
        FROM certificates
        WHERE telegram_id = ?
        {order_clause}
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("ℹ️ У вас пока нет сертификатов.")
        return

    response = "📄 Сертификаты: \\n"
    for i, (org, director, valid_to) in enumerate(rows, 1):
        valid_dt = datetime.fromisoformat(valid_to).date()
        response += f"{i}. 🏢 {org} | 👤 {director}\n   ⏳ До: {valid_dt}\n"
    await update.message.reply_text(response)

async def firm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return

    if not context.args:
        await update.message.reply_text("❗ Использование: /firm <часть названия фирмы>")
        return

    search_term = " ".join(context.args).lower()
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT organization, director, inn, edrpou, valid_from, valid_to
        FROM certificates
        WHERE telegram_id = ?
        AND LOWER(organization) LIKE ?
    ''', (user_id, f"%{search_term}%"))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Не найдено.")
        return

    response = ""
    for org, director, inn, edrpou, valid_from, valid_to in rows:
        valid_from = datetime.fromisoformat(valid_from).date()
        valid_to = datetime.fromisoformat(valid_to).date()
        response += (
            f"🏢 {org}\n👤 {director}\n"
            f"📅 {valid_from} — {valid_to}\n"
            f"🆔 ІНН: {inn} | ЄДРПОУ: {edrpou}\n\n"
        )
    await update.message.reply_text(response.strip())

async def add_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    if context.args:
        user_id = int(context.args[0])
        add_user(user_id)
        await update.message.reply_text(f"✅ Пользователь {user_id} добавлен.")
    else:
        await update.message.reply_text("❗ Использование: /adduser <user_id>")

async def remove_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    if context.args:
        user_id = int(context.args[0])
        remove_user(user_id)
        await update.message.reply_text(f"🗑 Пользователь {user_id} удалён.")
    else:
        await update.message.reply_text("❗ Использование: /removeuser <user_id>")

async def list_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    users = list_users()
    await update.message.reply_text("👥 Разрешённые пользователи:\n" + "\n".join(str(u) for u in users))

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("adduser", add_user_cmd))
    app.add_handler(CommandHandler("removeuser", remove_user_cmd))
    app.add_handler(CommandHandler("listusers", list_users_cmd))
    app.add_handler(CommandHandler("certs", certs_cmd))
    app.add_handler(CommandHandler("firm", firm_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()

if __name__ == "__main__":
    main()
