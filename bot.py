import asyncio
from notify import notify_users

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import BOT_TOKEN, ADMINS as ADMIN_IDS
from db import (
    init_db, insert_certificate, grant_access, revoke_access,
    get_shared_with, has_view_access, get_certificates_for_user, get_certificates_shared_with,
    get_user_language, set_user_language, get_all_user_ids, delete_expired_certificates
)

from cert_parser import parse_certificate
from utils import extract_zip, is_certificate_file
from i18n import translations
import os

def _(key, lang="ua"):
    from i18n import translations
    return translations.get(lang, translations["ua"]).get(key, key)

import tempfile
from datetime import datetime, time as dtime

init_db()

async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    buttons = [
        [
            InlineKeyboardButton(_(key="lang_uk", lang=lang), callback_data="lang_uk"),
            InlineKeyboardButton(_(key="lang_ru", lang=lang), callback_data="lang_ru"),
            InlineKeyboardButton(_(key="lang_en", lang=lang), callback_data="lang_en"),
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
        msg = _(key=f"lang_changed_{lang}", lang=lang)
        await query.edit_message_text(msg)


def main_menu_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [_(key="menu_upload", lang=lang), _(key="menu_my", lang=lang)],
            [_(key="menu_search", lang=lang), _(key="menu_access", lang=lang)]
        ],
        resize_keyboard=True
    )


def access_menu_keyboard(lang="ua"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(_(key="share_button", lang=lang), callback_data="share"),
            InlineKeyboardButton(_(key="unshare_button", lang=lang), callback_data="unshare"),
        ],
        [
            InlineKeyboardButton(_(key="shared_list_button", lang=lang), callback_data="shared_list")
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
            try:
                extract_zip(file_path, tmpdir)
                for root, _, files in os.walk(tmpdir):
                    for name in files:
                        if is_certificate_file(name):
                            cert_paths.append(os.path.join(root, name))
                if not cert_paths:
                    await update.message.reply_text(_(key="no_certs_in_archive", lang=lang))
                    return
            except Exception as e:
                await update.message.reply_text(_(key="archive_error", lang=lang).format(error=e))
                return
        elif is_certificate_file(document.file_name):
            cert_paths.append(file_path)
        else:
            await update.message.reply_text(_(key="unsupported_format", lang=lang))
            return

        added = 0
        skipped = 0
        errors = 0
        error_messages = []
        
        for cert_path in cert_paths:
            try:
                cert = parse_certificate(cert_path)
                filename = os.path.basename(cert_path)
                
                # Проверяем, что сертификат содержит необходимые данные
                if not cert.get("organization") or not cert.get("sha1"):
                    error_messages.append(_(key="incomplete_cert_data", lang=lang).format(filename=filename))
                    errors += 1
                    continue
                    
                if insert_certificate(cert, user_id, filename):
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                filename = os.path.basename(cert_path)
                error_messages.append(f"⚠️ {filename}: {e}")
                errors += 1
        
        # Отправляем результат
        if errors > 0:
            result_message = _(key="upload_result_with_errors", lang=lang).format(added=added, skipped=skipped, errors=errors)
        else:
            result_message = _(key="upload_result", lang=lang).format(added=added, skipped=skipped)
        await update.message.reply_text(result_message)
        
        # Отправляем детали ошибок, если есть
        if error_messages:
            error_text = "\n".join(error_messages[:5])  # Показываем максимум 5 ошибок
            if len(error_messages) > 5:
                error_text += "\n" + _(key="more_errors", lang=lang).format(count=len(error_messages) - 5)
            await update.message.reply_text(error_text)

async def certs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    from db import get_certificates_for_user, get_certificates_shared_with

    own = get_certificates_for_user(user_id)
    shared = get_certificates_shared_with(user_id)

    if not own and not shared:
        await update.message.reply_text(_(key="no_certificates", lang=lang))
        return

    lines = [_(key="your_certificates", lang=lang)]
    idx = 1

    if own:
        lines.append("\n" + _(key="own_certificates", lang=lang))
        for org, director, valid_to in own:
            try:
                dt = datetime.fromisoformat(valid_to)
                valid_date = dt.strftime("%d.%m.%Y")
            except:
                valid_date = valid_to
                dt = None

            if dt:
                today = datetime.today()
                days_left = (dt.date() - today.date()).days
                if days_left < 0:
                    status = "🟥"
                elif days_left < 7:
                    status = "⚠️"
                else:
                    status = "✅"
            else:
                status = "❔"

            lines.append(
                _(key="cert_format", lang=lang).format(idx=idx, status=status, org=org, director=director, valid_date=valid_date)
            )
            idx += 1

    if shared:
        lines.append("\n" + _(key="shared_certificates", lang=lang))
        for org, director, valid_to in shared:
            try:
                dt = datetime.fromisoformat(valid_to)
                valid_date = dt.strftime("%d.%m.%Y")
            except:
                valid_date = valid_to
                dt = None

            if dt:
                today = datetime.today()
                days_left = (dt.date() - today.date()).days
                if days_left < 0:
                    status = "🟥"
                elif days_left < 7:
                    status = "⚠️"
                else:
                    status = "✅"
            else:
                status = "❔"

            lines.append(
                _(key="shared_cert_format", lang=lang).format(idx=idx, status=status, org=org, director=director, valid_date=valid_date)
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
        await update.message.reply_text(_(key="access_menu", lang=lang), reply_markup=access_menu_keyboard(lang))

async def share_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    owner_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(_(key="share_usage", lang=lang))
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
        await update.message.reply_text(_(key="unshare_usage", lang=lang))
        return
    try:
        viewer_id = int(context.args[0])
        revoke_access(owner_id, viewer_id)
        await update.message.reply_text(f"{_(key='access_revoked', lang=lang)} {viewer_id}.")
    except:
        await update.message.reply_text(_(key="invalid_id", lang=lang))

async def shared_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    owner_id = update.effective_user.id
    viewers = get_shared_with(owner_id)
    if not viewers:
        await update.message.reply_text(_(key="no_shared_certs", lang=lang))
    else:
        await update.message.reply_text(_(key="shared_with", lang=lang).format(users="\n".join(str(u) for u in viewers)))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_user_language(user_id)

    if query.data == "share":
        await query.edit_message_text(_(key="share_instruction", lang=lang))
    elif query.data == "unshare":
        await query.edit_message_text(_(key="unshare_instruction", lang=lang))
    elif query.data == "shared_list":
        shared_ids = get_shared_with(user_id)
        if not shared_ids:
            await query.edit_message_text(_(key="no_certs_or_access", lang=lang))
        else:
            lines = [_(key="access_open_for", lang=lang)]
            for uid in shared_ids:
                lines.append(f"• ID: `{uid}`")
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
    else:
        await query.edit_message_text(_(key="unknown_command", lang=lang))

# ADMIN_IDS теперь импортируется из config.py (.env)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(_(key="no_admin_rights", lang=lang))
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text(_(key="broadcast_usage", lang=lang))
        return

    all_ids = get_all_user_ids()  # из базы
    count = 0
    for uid in all_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            count += 1
        except Exception:
            pass  # например, если пользователь заблокировал бота

    await update.message.reply_text(_(key="broadcast_sent", lang=lang).format(count=count))


def main():
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
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    async def cleanup_expired(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        lang = get_user_language(user_id)
        if user_id not in ADMIN_IDS:
            await update.message.reply_text(_(key="no_admin_rights", lang=lang))
            return
        deleted = delete_expired_certificates()
        await update.message.reply_text(_(key="cleanup_result", lang=lang).format(deleted=deleted))

    app.add_handler(CommandHandler("cleanup_expired", cleanup_expired))
    
    async def notify_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        lang = get_user_language(user_id)
        if user_id not in ADMIN_IDS:
            await update.message.reply_text(_(key="no_admin_rights", lang=lang))
            return
        await update.message.reply_text(_(key="notify_starting", lang=lang))
        await notify_users()
        await update.message.reply_text(_(key="notify_done", lang=lang))

    app.add_handler(CommandHandler("notify_now", notify_now))

    async def daily_notify_job(context: ContextTypes.DEFAULT_TYPE):
        await notify_users()

    local_tz = datetime.now().astimezone().tzinfo
    app.job_queue.run_daily(
        daily_notify_job,
        time=dtime(hour=7, minute=7, tzinfo=local_tz),
        name="daily_notify_job"
    )

    app.run_polling()

if __name__ == "__main__":
    main()
