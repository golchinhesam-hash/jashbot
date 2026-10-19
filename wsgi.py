# -*- coding: utf-8 -*-
"""
Gunicorn entry point for Render/Railway/Heroku deployment
این فایل برای اجرای بات روی سرور ابری استفاده می‌شه

نکته مهم: Render توی پلن web service منتظر می‌شه تا یه پورت باز بشه
پس یه وب‌سرور ساده (Flask) راه‌اندازی می‌کنیم که فقط برای health check هست
بات تلگرام توی یه thread جداگانه اجرا می‌شه

روش polling: مستقیم با Telegram Bot API (getUpdates) — نه از طریق python-telegram-bot async
چون asyncio توی thread غیر اصلی روی Render مشکل ایجاد می‌کنه
"""
import os
import logging
import sys
import threading
import time
import json
import requests as req_lib
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
app = Flask(__name__)

# Global bot instance for diagnostics
_bot_instance = None

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

@app.route("/debug")
def debug():
    """Diagnostic endpoint - tests API connectivity and scanning"""
    import sys
    sys.path.insert(0, '.')
    
    results = {"tests": []}
    
    # Test 1: Binance ping
    try:
        import requests
        for base in ["https://data-api.binance.vision", "https://api.binance.com"]:
            try:
                r = requests.get(f"{base}/api/v3/ping", timeout=5)
                results["tests"].append({"test": f"ping {base}", "status": r.status_code, "ok": r.status_code == 200})
            except Exception as e:
                results["tests"].append({"test": f"ping {base}", "error": str(e), "ok": False})
    except Exception as e:
        results["tests"].append({"test": "requests import", "error": str(e), "ok": False})
    
    # Test 2: Binance klines
    try:
        r = requests.get("https://data-api.binance.vision/api/v3/klines", 
                         params={"symbol": "BTCUSDT", "interval": "1h", "limit": 5}, timeout=10)
        results["tests"].append({"test": "binance klines", "status": r.status_code, "data_count": len(r.json()) if r.status_code == 200 else 0, "ok": r.status_code == 200})
    except Exception as e:
        results["tests"].append({"test": "binance klines", "error": str(e), "ok": False})
    
    # Test 3: Bybit klines
    try:
        r = requests.get("https://api.bybit.com/v5/market/kline",
                         params={"category": "spot", "symbol": "BTCUSDT", "interval": "60", "limit": 5}, timeout=10)
        data = r.json()
        results["tests"].append({"test": "bybit klines", "status": r.status_code, "retCode": data.get("retCode"), "data_count": len(data.get("result",{}).get("list",[])), "ok": data.get("retCode") == 0})
    except Exception as e:
        results["tests"].append({"test": "bybit klines", "error": str(e), "ok": False})
    
    # Test 4: Bybit ticker
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers", 
                         params={"category": "spot"}, timeout=10)
        data = r.json()
        results["tests"].append({"test": "bybit tickers", "status": r.status_code, "retCode": data.get("retCode"), "data_count": len(data.get("result",{}).get("list",[])), "ok": data.get("retCode") == 0})
    except Exception as e:
        results["tests"].append({"test": "bybit tickers", "error": str(e), "ok": False})
    
    # Test 5: Bot instance status
    if _bot_instance:
        results["bot_status"] = {
            "running": _bot_instance.running,
            "chat_id": _bot_instance.chat_id,
            "last_signals_count": len(_bot_instance.last_signals),
            "whale_alerts_count": len(_bot_instance.whale_alerts),
            "radar_running": _bot_instance.radar.running if hasattr(_bot_instance, 'radar') else False,
        }
    else:
        results["bot_status"] = {"running": False, "error": "bot not initialized yet"}
    
    # Test 6: Quick signal test on BTC
    try:
        from core.market_data import MarketData
        md = MarketData()
        candles = md.get_candles("BTCUSDT", "1h", 100)
        results["tests"].append({"test": "get_candles BTCUSDT", "candles": len(candles), "ok": len(candles) > 0})
        
        if candles and len(candles) > 5:
            from core.signal_engine import SignalEngine
            engine = SignalEngine(md)
            signal = engine.scan_symbol("BTCUSDT", "BTC", is_shitcoin=False)
            if signal:
                results["tests"].append({
                    "test": "signal BTCUSDT",
                    "direction": signal.get("direction"),
                    "score": signal.get("score", 0),
                    "ok": True
                })
            else:
                results["tests"].append({"test": "signal BTCUSDT", "error": "returned None", "ok": False})
    except Exception as e:
        results["tests"].append({"test": "signal BTCUSDT", "error": str(e), "ok": False})
    
    return jsonify(results)


# ===================== Manual Telegram Polling =====================
def run_bot():
    """اجرای بات تلگرام با polling مستقیم (بدون async)"""
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

        # شروع بات و اسکنر
        from core.telegram_bot import TelegramBot
        bot = TelegramBot()
        global _bot_instance
        _bot_instance = bot

        if TELEGRAM_CHAT_ID:
            bot.chat_id = TELEGRAM_CHAT_ID
            bot.start_scanner_loop()
            if not bot.radar.running:
                bot.radar.start()

        logger.info("🚀 بات روی سرور شروع شد - 24/7 فعال")

        # ===================== Polling Loop =====================
        # مستقیم با Telegram API — بدون asyncio
        base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        offset = 0  # برای ack کردن update‌ها
        timeout_long = 30  # long polling timeout

        logger.info("📡 شروع polling مستقیم Telegram API...")

        while True:
            try:
                params = {"timeout": timeout_long, "limit": 10}
                if offset > 0:
                    params["offset"] = offset

                resp = req_lib.get(
                    f"{base_url}/getUpdates",
                    params=params,
                    timeout=timeout_long + 10
                )

                if resp.status_code != 200:
                    logger.error(f"خطا getUpdates: {resp.status_code} {resp.text[:200]}")
                    time.sleep(5)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    logger.error(f"getUpdates not ok: {data}")
                    time.sleep(5)
                    continue

                updates = data.get("result", [])
                for update in updates:
                    offset = update.get("update_id") + 1

                    msg = update.get("message")
                    if not msg:
                        continue

                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")
                    first_name = msg.get("from", {}).get("first_name", "")

                    logger.info(f"📨 پیام دریافت شد: '{text}' از {first_name} (chat_id={chat_id})")

                    # پردازش دستورات
                    if text.startswith("/start"):
                        handle_start(bot, chat_id, first_name)
                    elif text.startswith("/adduser"):
                        handle_adduser(bot, chat_id, text)
                    elif text.startswith("/users"):
                        handle_users(bot, chat_id)
                    elif text.startswith("/status"):
                        handle_status(bot, chat_id)
                    elif text.startswith("/scan"):
                        handle_scan(bot, chat_id)
                    elif text.startswith("/radar"):
                        handle_radar(bot, chat_id)
                    elif text.startswith("/last"):
                        handle_last(bot, chat_id)
                    elif text.startswith("/help"):
                        handle_help(bot, chat_id)

            except req_lib.exceptions.Timeout:
                # normal for long polling
                continue
            except Exception as e:
                logger.error(f"خطا در حلقه polling: {e}")
                time.sleep(5)

    except Exception as e:
        logger.error(f"خطای بحرانی بات: {e}")
        logger.info("ری‌استارت بات بعد از 10 ثانیه...")
        time.sleep(10)
        run_bot()


# ===================== Command Handlers =====================
def send_message(token, chat_id, text, parse_mode="Markdown"):
    """ارسال پیام به تلگرام"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = req_lib.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }, timeout=15)
        return resp.json().get("ok", False)
    except Exception as e:
        logger.error(f"خطا در ارسال: {e}")
        return False


def is_authorized(chat_id):
    """بررسی دسترسی - فقط آیدی‌های مجاز"""
    import config
    return chat_id in config.AUTHORIZED_CHAT_IDS


def send_unauthorized_message(token, chat_id):
    """پیام به کاربر غیرمجاز"""
    msg = (
        "🔒 **این ربات خصوصی است**\n\n"
        "شما اجازه استفاده از این ربات را ندارید.\n"
        "اگر فکر می‌کنید اشتباهی شده، با مدیر تماس بگیرید."
    )
    send_message(token, chat_id, msg)


def handle_start(bot, chat_id, first_name):
    """پردازش /start"""
    import config

    # بررسی دسترسی
    if not is_authorized(chat_id):
        logger.warning(f"کاربر غیرمجاز {first_name} (ID: {chat_id}) تلاش کرد /start بزنه")
        send_unauthorized_message(config.TELEGRAM_BOT_TOKEN, chat_id)
        return

    bot.chat_id = chat_id
    config.TELEGRAM_CHAT_ID = chat_id
    if not config.ADMIN_IDS:
        config.ADMIN_IDS = [chat_id]

    logger.info(f"کاربر {first_name} (ID: {chat_id}) بات رو استارت زد")

    msg = (
        f"🤖 ربات سیگنال کریپتو + Whale Radar\n\n"
        f"سلام {first_name}! چت آیدی شما ثبت شد: `{chat_id}`\n\n"
        f"🔒 **این ربات خصوصی است** - فقط کاربران مجاز می‌تونن استفاده کنن.\n\n"
        f"من بازار ارزهای دیجیتال رو اسکن می‌کنم و "
        f"سیگنال‌های خرید و فروش با تحلیل زیر ارائه می‌دم:\n\n"
        f"📊 Order Flow - جریان سفارشات\n"
        f"💧 Liquidity - نواحی نقدینگی\n"
        f"🐋 Whale Scanner - فعالیت نهنگ‌ها\n"
        f"⚡ Whale Radar - هشدار لحظه‌ای نهنگ (WebSocket)\n\n"
        f"دستورات:\n"
        f"/status - وضعیت بات\n"
        f"/scan - اسکن دستی بازار\n"
        f"/radar - وضعیت Whale Radar لحظه‌ای\n"
        f"/last - آخرین سیگنال‌ها\n"
        f"/users - لیست کاربران مجاز\n"
        f"/help - راهنما\n\n"
        f"⚡ Whale Radar فعال شد - هشدار نهنگ‌ها رو لحظه‌ای می‌گیری"
    )
    send_message(config.TELEGRAM_BOT_TOKEN, chat_id, msg)

    if not bot.running:
        bot.start_scanner_loop()
    if not bot.radar.running:
        bot.radar.start()


def handle_status(bot, chat_id):
    """پردازش /status"""
    import config
    if not is_authorized(chat_id):
        send_unauthorized_message(config.TELEGRAM_BOT_TOKEN, chat_id)
        return
    status = "✅ فعال" if bot.running else "❌ غیرفعال"
    radar_stats = bot.radar.get_stats()
    binance_stats = radar_stats.get("binance", {})
    bybit_stats = radar_stats.get("bybit", {})

    msg = (
        f"📊 وضعیت بات\n\n"
        f"اسکنر دوره‌ای: {status}\n"
        f"فاصله اسکن: {config.SCAN_INTERVAL} ثانیه\n"
        f"تعداد سیگنال ارسالی: {len(bot.last_signals)}\n"
        f"چت آیدی: {bot.chat_id or config.TELEGRAM_CHAT_ID}\n\n"
        f"🐋 Whale Radar:\n"
        f"  وضعیت کلی: {'✅' if radar_stats.get('running') else '❌'}\n"
        f"  ارزهای پایش: {radar_stats.get('symbols_count', 0)}\n"
        f"  کل هشدارها: {radar_stats.get('total_alerts', 0)}\n\n"
        f"  Binance:\n"
        f"    اتصال: {'✅' if binance_stats.get('connected') else '❌'}\n"
        f"    ترید‌ها: {binance_stats.get('total_trades', 0)}\n"
        f"    نهنگ: {binance_stats.get('whale_trades', 0)}\n"
        f"    هشدار: {binance_stats.get('alerts_sent', 0)}\n\n"
        f"  Bybit:\n"
        f"    اتصال: {'✅' if bybit_stats.get('connected') else '❌'}\n"
        f"    ترید‌ها: {bybit_stats.get('total_trades', 0)}\n"
        f"    نهنگ: {bybit_stats.get('whale_trades', 0)}\n"
        f"    هشدار: {bybit_stats.get('alerts_sent', 0)}\n\n"
        f"  آخرین به‌روزرسانی: {time.strftime('%H:%M:%S')}"
    )
    send_message(config.TELEGRAM_BOT_TOKEN, chat_id, msg)


def handle_scan(bot, chat_id):
    """پردازش /scan"""
    import config
    if not is_authorized(chat_id):
        send_unauthorized_message(config.TELEGRAM_BOT_TOKEN, chat_id)
        return
    send_message(config.TELEGRAM_BOT_TOKEN, chat_id, "🔍 شروع اسکن ۳۲۶ ارز... مراحل رو برات می‌فرستم")

    def progress_cb(msg):
        """ارسال پیام پیشرفت به تلگرام"""
        send_message(config.TELEGRAM_BOT_TOKEN, chat_id, msg)

    def do_scan():
        try:
            found = bot.run_market_scan(progress_callback=progress_cb)
            if found:
                send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
                    f"📨 {len(found)} سیگنال ارسال شد!")
            else:
                send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
                    "❌ هیچ سیگنال معتبری در حال حاضر یافت نشد.\n💡 بازار رو خنثی می‌کنه - صبر کن تا شرایط عوض شه")
        except Exception as e:
            logger.error(f"خطا در اسکن: {e}")
            send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
                f"⚠️ خطا در اسکن: {e}")

    thread = threading.Thread(target=do_scan)
    thread.start()


def handle_radar(bot, chat_id):
    """پردازش /radar"""
    import config
    if not is_authorized(chat_id):
        send_unauthorized_message(config.TELEGRAM_BOT_TOKEN, chat_id)
        return
    stats = bot.radar.get_stats()
    if not bot.radar.running:
        send_message(config.TELEGRAM_BOT_TOKEN, chat_id, "❌ Whale Radar فعال نیست. /start بزنید.")
        return

    msg = (
        f"🐋 Whale Radar - وضعیت لحظه‌ای\n\n"
        f"🔗 Binance: {'✅ متصل' if stats.get('binance', {}).get('connected') else '❌ قطع'}\n"
        f"🔗 Bybit: {'✅ متصل' if stats.get('bybit', {}).get('connected') else '❌ قطع'}\n"
        f"📊 ارزهای پایش: {stats.get('symbols_count', 0)}\n"
        f"⚡ کل هشدارها: {stats.get('total_alerts', 0)}\n\n"
        f"آخرین هشدارها:\n"
    )

    if bot.whale_alerts:
        for a in bot.whale_alerts[-5:]:
            emoji = "🟢" if a.get("direction") == "buy" else "🔴"
            alert_type = a.get("type", "")
            if alert_type == "SINGLE_WHALE":
                msg += (
                    f"  {emoji} {a.get('base', '')} - {a.get('direction_farsi', '')} "
                    f"{a.get('value_usdt', 0)/1e6:.1f}M "
                    f"({a.get('exchange', '')}) "
                    f"@ {a.get('time_str', '')}\n"
                )
            else:
                msg += (
                    f"  {emoji} {a.get('base', '')} - {a.get('direction_farsi', '')} "
                    f"{a.get('cluster_count', 0)} ترید "
                    f"({a.get('total_value_usdt', 0)/1e6:.1f}M) "
                    f"@ {a.get('time_str', '')}\n"
                )
    else:
        msg += "  هنوز هشداری دریافت نشده.\n"

    msg += f"\n⏰ {time.strftime('%H:%M:%S')}"
    send_message(config.TELEGRAM_BOT_TOKEN, chat_id, msg)


def handle_last(bot, chat_id):
    """پردازش /last"""
    import config
    if not bot.last_signals:
        send_message(config.TELEGRAM_BOT_TOKEN, chat_id, "📭 هنوز سیگنالی ارسال نشده.")
        return

    msg = "📋 **آخرین سیگنال‌ها:**\n\n"
    for s in bot.last_signals[-5:]:
        direction_emoji = "🟢" if s.get("direction") == "LONG" else "🔴"
        msg += (
            f"{direction_emoji} **{s.get('base', s.get('symbol', ''))}** "
            f"- {s.get('direction')} "
            f"(امتیاز: {s.get('score', 0):.0f})\n"
            f"   ورود: {s.get('entry', 0):.4f}\n\n"
        )

    send_message(config.TELEGRAM_BOT_TOKEN, chat_id, msg)


def handle_help(bot, chat_id):
    """پردازش /help"""
    import config
    msg = (
        "📖 **راهنمای ربات**\n\n"
        "**دستورات:**\n"
        "/start - معرفی ربات\n"
        "/status - وضعیت فعلی\n"
        "/scan - اسکن دستی بازار\n"
        "/last - آخرین سیگنال‌ها\n"
        "/help - این راهنما\n\n"
        "**روش تحلیل:**\n"
        "این ربات ارزهای USDT رو بر اساس 3 معیار تحلیل می‌کنه:\n\n"
        "1️⃣ **Order Flow:** جریان خرید و فروش\n"
        "2️⃣ **Liquidity:** حمایت/مقاومت و استخر نقدینگی\n"
        "3️⃣ **Whale Activity:** فعالیت نهنگ‌ها و CVD\n\n"
        "**معیار سیگنال:**\n"
        "• حداقل 10% سود مورد انتظار\n"
        "• حداقل 2:1 Risk/Reward\n"
        "• استاپ لاس دقیق زیر حمایت/بالای مقاومت\n\n"
        "⚠️ مسئولیت معامله با شماست."
    )
    send_message(config.TELEGRAM_BOT_TOKEN, chat_id, msg)


def handle_adduser(bot, chat_id, text):
    """اضافه کردن کاربر جدید - فقط برای ادمین اصلی"""
    import config

    # فقط ادمین اصلی (اولین آیدی) می‌تونه کاربر اضافه کنه
    if not config.AUTHORIZED_CHAT_IDS or chat_id != config.AUTHORIZED_CHAT_IDS[0]:
        send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
            "❌ فقط ادمین اصلی می‌تونه کاربر اضافه کنه.")
        return

    # فرمت: /adduser 123456789
    parts = text.split()
    if len(parts) < 2:
        send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
            "❌ فرمت اشتباه.\n"
            "نحوه استفاده:\n"
            "`/adduser 123456789`\n\n"
            "برای گرفتن آیدی: کاربر باید به @userinfobot پیام بده.")
        return

    try:
        new_id = int(parts[1])
    except ValueError:
        send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
            "❌ آیدی باید عدد باشه. مثال: `/adduser 123456789`")
        return

    if new_id in config.AUTHORIZED_CHAT_IDS:
        send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
            f"ℹ️ آیدی `{new_id}` قبلاً توی لیست هست.")
        return

    config.AUTHORIZED_CHAT_IDS.append(new_id)
    send_message(config.TELEGRAM_BOT_TOKEN, chat_id,
        f"✅ آیدی `{new_id}` به لیست مجاز اضافه شد.\n\n"
        f"📋 تعداد کاربران مجاز: {len(config.AUTHORIZED_CHAT_IDS)}")
    logger.info(f"کاربر جدید اضافه شد: {new_id} توسط ادمین {chat_id}")


def handle_users(bot, chat_id):
    """لیست کاربران مجاز - فقط برای ادمین"""
    import config

    if not is_authorized(chat_id):
        send_unauthorized_message(config.TELEGRAM_BOT_TOKEN, chat_id)
        return

    msg = "👥 **لیست کاربران مجاز:**\n\n"
    for i, uid in enumerate(config.AUTHORIZED_CHAT_IDS, 1):
        admin_tag = " (ادمین اصلی)" if i == 1 else ""
        msg += f"{i}. `{uid}`{admin_tag}\n"

    msg += f"\n📊 تعداد کل: {len(config.AUTHORIZED_CHAT_IDS)}"
    send_message(config.TELEGRAM_BOT_TOKEN, chat_id, msg)


# شروع بات توی thread جدا قبل از اجرای وب‌سرور
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

# این فقط وقتی مستقیم اجرا بشه (نه با Gunicorn)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 وب‌سرور روی پورت {port} شروع شد")
    app.run(host="0.0.0.0", port=port, debug=False)
