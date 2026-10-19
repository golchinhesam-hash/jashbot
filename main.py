# -*- coding: utf-8 -*-
"""
بات سیگنال کریپتو - فایل اصلی اجرا
تحلیل: Order Flow + Liquidity + Whale Activity
خروجی: سیگنال خرید/فروش در تلگرام با Entry, SL, TP
"""

import logging
import sys
import os

# اضافه کردن مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_LEVEL, LOG_FILE
from core.telegram_bot import TelegramBot


def setup_logging():
    """تنظیم لاگ‌گذاری"""
    level = getattr(logging, LOG_LEVEL, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def check_config():
    """بررسی تنظیمات"""
    logger = logging.getLogger(__name__)

    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error("❌ توکن بات تلگرام تنظیم نشده!")
        sys.exit(1)

    logger.info("✅ توکن تلگرام تنظیم شده - بات آماده")
    if TELEGRAM_CHAT_ID:
        logger.info(f"✅ چت آیدی موجود: {TELEGRAM_CHAT_ID}")
    else:
        logger.info("ℹ️ چت آیدی بعد از /start خودکار تنظیم میشه")


def main():
    """نقطه ورودی اصلی"""
    setup_logging()
    logger = logging.getLogger(__name__)

    print("=" * 50)
    print("  🤖 بات سیگنال کریپتو")
    print("  📊 Order Flow + Liquidity + Whale Scanner")
    print("=" * 50)
    print()

    check_config()

    logger.info("🚀 شروع بات...")
    bot = TelegramBot()

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("بات متوقف شد")
        sys.exit(0)
    except Exception as e:
        logger.error(f"خطای بحرانی: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
