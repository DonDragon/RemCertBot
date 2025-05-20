
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Bot
from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)

def get_users_with_cert_expiring(days_ahead: int):
    conn = sqlite3.connect("certificates.db")
    cursor = conn.cursor()

    target_date = (datetime.utcnow() + timedelta(days=days_ahead)).date()
    cursor.execute('''
        SELECT telegram_id, organization, director, valid_to
        FROM certificates
        WHERE DATE(valid_to) = ?
    ''', (target_date.isoformat(),))
    results = cursor.fetchall()
    conn.close()
    return results

async def notify_users():
    for days in [30, 7, 0]:
        certs = get_users_with_cert_expiring(days)
        for telegram_id, org, director, valid_to in certs:
            valid_to = datetime.fromisoformat(valid_to).date()
            if days == 0:
                msg = f"⚠️ Сегодня истекает срок действия сертификата: 🏢 {org} 👤 {director}"
            else:
                msg = f"🔔 Через {days} дней истекает сертификат:🏢 {org} 👤 {director} ⏳ До: {valid_to}"

            try:
                await bot.send_message(chat_id=telegram_id, text=msg)
            except Exception as e:
                print(f"Ошибка отправки для {telegram_id}: {e}")

if __name__ == "__main__":
    asyncio.run(notify_users())
