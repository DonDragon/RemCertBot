
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "share":
        await query.edit_message_text("✉️ Введите команду /share <user_id>, чтобы поделиться доступом.")
    elif query.data == "unshare":
        await query.edit_message_text("🧹 Введите команду /unshare <user_id>, чтобы отозвать доступ.")
    elif query.data == "shared_list":
        from db import get_shared_with
        shared_ids = get_shared_with(user_id)
        if not shared_ids:
            await query.edit_message_text("👤 У вас нет добавленных сертификатов или доступ не передавался.")
        else:
            lines = [f"🔐 Доступ открыт для:"]
            for uid in shared_ids:
                lines.append(f"• ID: `{uid}`")
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
    else:
        await query.edit_message_text("⚠️ Неизвестная команда.")
