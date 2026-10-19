# -*- coding: utf-8 -*-
"""
Gunicorn entry point for Render/Railway/Heroku deployment
این فایل برای اجرای بات روی سرور ابری استفاده می‌شه
"""
import os
import logging
import sys

# تنظیم لاگ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

def main():
    """اجرای بات روی سرور"""
    print("=" * 50)
    print("  🤖 بات سیگنال کریپتو - Cloud Deployment")
    print("  📊 Order Flow + Liquidity + Whale Scanner")
    print("  🌍 اجرا روی سرور ابری - نیازی به لپ‌تاپ نیست")
    print("=" * 50)

    # بررسی متغیرهای محیطی
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ توکن تلگرام تنظیم نشده!")
        sys.exit(1)

    logger.info("✅ توکن تلگرام تنظیم شده")

    # اگه چت آیدی تنظیم شده باشه، اسکنر خودکار شروع می‌شه
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

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("بات متوقف شد")
        sys.exit(0)
    except Exception as e:
        logger.error(f"خطای بحرانی: {e}")
        sys.exit(1)

# این بخش برای Render لازمه - Gunicorn بهش نیاز داره
# ولی چون بات polling استفاده می‌کنه، فقط main() رو اجرا می‌کنیم
if __name__ == "__main__":
    main()
