# -*- coding: utf-8 -*-
"""
بات سیگنال کریپتو - نسخه کاملاً خودکار
تحلیل: Order Flow + Liquidity + Whale + ZoneHunter + OF Matrix + Market Context + Funding
خروجی: سیگنال خودکار در کانال تلگرام

نیازی به PC یا دستور نیست - کاملاً خودکار روی Render
"""

import logging
import sys
import os
import time
import threading
import requests

# اضافه کردن مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID,
    LOG_LEVEL, LOG_FILE, SCAN_INTERVAL
)
from core.market_data import MarketData
from core.signal_engine import SignalEngine
from core.autonomous_scheduler import AutonomousScheduler

logger = logging.getLogger(__name__)


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


def send_to_telegram(message):
    """ارسال پیام به کانال و چت (تابع مستقل برای scheduler)"""
    # 1. ارسال به کانال
    if TELEGRAM_CHANNEL_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TELEGRAM_CHANNEL_ID, "text": message, "parse_mode": "Markdown"}
            resp = requests.post(url, data=data, timeout=15)
            if resp.status_code == 200:
                logger.info("پیام به کانال ارسال شد")
            else:
                logger.error(f"خطا در ارسال به کانال: {resp.text}")
        except Exception as e:
            logger.error(f"خطا در ارسال به کانال: {e}")

    # 2. ارسال به چت خصوصی (backup)
    if TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
            requests.post(url, data=data, timeout=15)
        except Exception as e:
            logger.error(f"خطا در ارسال به چت: {e}")


def main():
    """نقطه ورودی اصلی - کاملاً خودکار"""
    setup_logging()
    logger.info("=" * 60)
    logger.info("🤖 CRYPTO SIGNAL BOT - AUTONOMOUS MODE")
    logger.info("📊 9 Systems | 24/7 | No Human Required")
    logger.info("=" * 60)

    # بررسی تنظیمات
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error("❌ توکن بات تلگرام تنظیم نشده!")
        sys.exit(1)

    logger.info("✅ تنظیمات OK")
    logger.info(f"   کانال: {TELEGRAM_CHANNEL_ID}")
    logger.info(f"   چت: {TELEGRAM_CHAT_ID}")
    logger.info(f"   فاصله اسکن: {SCAN_INTERVAL} ثانیه")

    # ساخت موتورها
    logger.info("🔧 راه‌اندازی موتورها...")
    market = MarketData()
    engine = SignalEngine(market)

    # ساخت scheduler خودکار
    scheduler = AutonomousScheduler(
        engine=engine,
        market=market,
        telegram_sender=send_to_telegram
    )

    # شروع خودکار - بدون نیاز به /start!
    logger.info("🚀 شروع سیستم خودکار...")
    scheduler.start()

    # حلقه اصلی - فقط برای نگه داشتن برنامه زنده
    logger.info("✅ بات کاملاً خودکار فعال شد!")
    logger.info("💤 حلقه اصلی در حال اجرا...")

    try:
        while True:
            time.sleep(60)
            # چک کردن اینکه scheduler هنوز ران هست
            if not scheduler.running:
                logger.warning("⚠️ Scheduler متوقف شده - راه‌اندازی مجدد...")
                scheduler.start()
    except KeyboardInterrupt:
        logger.info("بات متوقف شد (KeyboardInterrupt)")
        scheduler.stop()
        sys.exit(0)
    except Exception as e:
        logger.error(f"خطای بحرانی: {e}")
        scheduler.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
