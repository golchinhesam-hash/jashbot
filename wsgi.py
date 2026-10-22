# -*- coding: utf-8 -*-
"""
Gunicorn entry point for Render - AUTONOMOUS MODE
کاملاً خودکار - نیازی به PC یا دستور نیست

نسخه جدید با 9 سیستم:
- Order Flow, Liquidity, Whale, ZoneHunter, OF Matrix
- Market Context (BTC + ADX), Funding/OI
"""
import os
import logging
import sys
import threading
import time
import requests as req_lib
from flask import Flask, jsonify

# تنظیم لاگ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ===================== Flask Web Server (Health Check) =====================
app = Flask(__name__)

_scheduler = None
_start_time = time.time()
_scan_count = 0
_signal_count = 0


@app.route("/")
def health():
    """Health check برای Render"""
    uptime = int(time.time() - _start_time)
    return jsonify({
        "status": "ok",
        "mode": "AUTONOMOUS",
        "uptime_seconds": uptime,
        "uptime_human": f"{uptime // 3600}h {(uptime % 3600) // 60}m",
        "scans": _scan_count,
        "signals": _signal_count,
        "systems": 9,
        "message": "Crypto Signal Bot - Autonomous 24/7"
    })


@app.route("/health")
def health_check():
    return "OK", 200


# ===================== Autonomous Bot Runner =====================
def run_autonomous_bot():
    """اجرای بات کاملاً خودکار روی Render"""
    global _scheduler, _scan_count, _signal_count

    sys.path.insert(0, '.')

    try:
        from config import (
            TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
            TELEGRAM_CHAT_ID, SCAN_INTERVAL
        )
        from core.market_data import MarketData
        from core.signal_engine import SignalEngine
        from core.autonomous_scheduler import AutonomousScheduler

        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ توکن تلگرام تنظیم نشده!")
            return

        logger.info("=" * 60)
        logger.info("🤖 AUTONOMOUS SIGNAL BOT - Starting on Render")
        logger.info("📊 9 Systems | 24/7 | No Human Required")
        logger.info("=" * 60)

        # تابع ارسال پیام
        def send_message(msg):
            """ارسال به کانال و چت"""
            # کانال
            if TELEGRAM_CHANNEL_ID:
                try:
                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    data = {
                        "chat_id": TELEGRAM_CHANNEL_ID,
                        "text": msg,
                        "parse_mode": "Markdown",
                    }
                    resp = req_lib.post(url, data=data, timeout=15)
                    if resp.status_code == 200:
                        logger.info("📨 پیام به کانال ارسال شد")
                except Exception as e:
                    logger.error(f"خطا در ارسال به کانال: {e}")

            # چت خصوصی
            if TELEGRAM_CHAT_ID:
                try:
                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    data = {
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": msg,
                        "parse_mode": "Markdown",
                    }
                    req_lib.post(url, data=data, timeout=15)
                except Exception as e:
                    logger.error(f"خطا در ارسال به چت: {e}")

        # ساخت موتورها
        logger.info("🔧 Initializing engines...")
        market = MarketData()
        engine = SignalEngine(market)

        # ساخت scheduler
        _scheduler = AutonomousScheduler(
            engine=engine,
            market=market,
            telegram_sender=send_message
        )

        # شروع خودکار - بدون نیاز به /start!
        logger.info("🚀 Starting autonomous scheduler...")
        _scheduler.start()

        logger.info("✅ BOT IS FULLY AUTONOMOUS!")
        logger.info(f"⏱️ Scan interval: {SCAN_INTERVAL} seconds")
        logger.info("💤 Main thread keeping alive...")

        # حلقه اصلی - نگه داشتن برنامه
        while True:
            time.sleep(300)  # هر 5 دقیقه
            if _scheduler:
                _scan_count = _scheduler.scan_count
                _signal_count = _scheduler.signal_count
                logger.info(
                    f"💓 Alive | Scans: {_scan_count} | "
                    f"Signals: {_signal_count} | "
                    f"Errors: {_scheduler.error_count}"
                )

    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        logger.info("🔄 Restarting in 30 seconds...")
        time.sleep(30)
        run_autonomous_bot()  # ری‌استارت


# شروع بات توی thread جدا
bot_thread = threading.Thread(target=run_autonomous_bot, daemon=True)
bot_thread.start()
logger.info("🚀 Autonomous bot thread started")

# وب‌سرور (فقط برای health check Render)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 Web server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
