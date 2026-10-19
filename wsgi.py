# -*- coding: utf-8 -*-
"""
Gunicorn entry point for Render/Railway/Heroku deployment
این فایل برای اجرای بات روی سرور ابری استفاده می‌شه

نکته مهم: Render توی پلن web service منتظر می‌شه تا یه پورت باز بشه
پس یه وب‌سرور ساده (Flask) راه‌اندازی می‌کنیم که فقط برای health check هست
بات تلگرام توی یه thread جداگانه اجرا می‌شه
"""
import os
import logging
import sys
import threading
import time
from flask import Flask, jsonify

# تنظیم لاگ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# ===================== Flask Web Server =====================
# این فقط برای health check Render هست
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "bot": "running",
        "message": "Crypto Signal Bot is active 24/7"
    })

@app.route("/health")
def health_check():
    return "OK", 200


# ===================== Bot Thread =====================
def run_bot():
    """اجرای بات تلگرام توی thread جداگانه"""
    try:
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ توکن تلگرام تنظیم نشده!")
            return

        logger.info("✅ توکن تلگرام تنظیم شده")

        if TELEGRAM_CHAT_ID:
            logger.info(f"✅ چت آیدی موجود: {TELEGRAM_CHAT_ID}")
        else:
            logger.info("ℹ️ چت آیدی بعد از /start خودکار تنظیم می‌شه")

        # شروع بات
        from core.telegram_bot import TelegramBot
        bot = TelegramBot()

        # اگه چت آیدی موجود بود، اسکنر رو شروع کن
        if TELEGRAM_CHAT_ID:
            bot.chat_id = TELEGRAM_CHAT_ID
            bot.start_scanner_loop()
            if not bot.radar.running:
                bot.radar.start()

        logger.info("🚀 بات روی سرور شروع شد - 24/7 فعال")

        # اجرای polling بات (توی همین thread)
        bot.run()

    except Exception as e:
        logger.error(f"خطای بحرانی بات: {e}")
        # restart بعد از 10 ثانیه
        logger.info("ری‌استارت بات بعد از 10 ثانیه...")
        time.sleep(10)
        run_bot()


# شروع بات توی thread جدا قبل از اجرای وب‌سرور
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

# این فقط وقتی مستقیم اجرا بشه (نه با Gunicorn)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 وب‌سرور روی پورت {port} شروع شد")
    app.run(host="0.0.0.0", port=port, debug=False)
