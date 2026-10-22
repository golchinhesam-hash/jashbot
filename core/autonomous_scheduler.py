# -*- coding: utf-8 -*-
"""
Autonomous Signal Scheduler
سیستم خودکار اسکن و ارسال سیگنال
بدون نیاز به /start یا هیچ دستوری
"""

import logging
import time
import threading
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)


class AutonomousScheduler:
    """
    زمان‌بند خودکار برای اسکن بازار و ارسال سیگنال
    - اسکن دوره‌ای هر 8 دقیقه
    - بررسی سلامت بات هر 1 دقیقه
    - ریکاوری خودکار از خطا
    """

    def __init__(self, engine, market, telegram_sender):
        self.engine = engine
        self.market = market
        self.telegram_sender = telegram_sender  # تابع ارسال پیام
        self.running = False
        self.scan_thread = None
        self.health_thread = None
        self.last_scan_time = 0
        self.last_signal_time = 0
        self.scan_count = 0
        self.signal_count = 0
        self.error_count = 0
        self.consecutive_errors = 0

    def start(self):
        """شروع سیستم خودکار - بدون نیاز به هیچ دستوری"""
        if self.running:
            logger.info("سیستم خودکار قبلاً ران هست")
            return

        self.running = True
        logger.info("🚀 شروع سیستم خودکار - Autonomous Mode Activated")

        # ارسال پیام راه‌اندازی به کانال
        self._send_startup_message()

        # شروع ترد اسکن
        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()

        # شروع ترد سلامت
        self.health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self.health_thread.start()

        logger.info("✅ تمام تردها شروع شدن - بات کاملاً خودکاره!")

    def stop(self):
        """توقف سیستم"""
        self.running = False
        logger.info("سیستم خودکار متوقف شد")

    def _send_startup_message(self):
        """پیام راه‌اندازی به کانال"""
        from config import SCAN_INTERVAL
        msg = (
            "🤖 **بات سیگنال کریپتو - راه‌اندازی شد**\n\n"
            "✅ سیستم کاملاً خودکار فعال شد\n"
            "📊 9 سیستم تحلیل در حال کار\n"
            f"⏱️ فاصله اسکن: هر {SCAN_INTERVAL // 60} دقیقه\n"
            "🌐 کریپتو 24/7 - هیچ محدودیت ساعتی\n\n"
            "🎯 سیستم‌ها:\n"
            "  1️⃣ Order Flow\n"
            "  2️⃣ Liquidity Scanner\n"
            "  3️⃣ Whale Scanner\n"
            "  4️⃣ Whale Hunter\n"
            "  5️⃣ Pre-Movement Detector\n"
            "  6️⃣ ZoneHunter\n"
            "  7️⃣ Order Flow Matrix PRO\n"
            "  8️⃣ Market Context (BTC + ADX)\n"
            "  9️⃣ Funding/OI Analyzer\n\n"
            "⚡ سیگنال‌ها خودکار ارسال میشن - نیازی به دستور نیست!"
        )
        try:
            self.telegram_sender(msg)
        except Exception as e:
            logger.error(f"خطا در ارسال پیام راه‌اندازی: {e}")

    def _scan_loop(self):
        """حلقه اصلی اسکن - هر 8 دقیقه"""
        from config import SCAN_INTERVAL

        # اسکن اولیه با کمی تأخیر (5 ثانیه) برای اطمینان از اتصال
        time.sleep(5)

        while self.running:
            try:
                self._do_single_scan()
                self.consecutive_errors = 0
            except Exception as e:
                self.error_count += 1
                self.consecutive_errors += 1
                logger.error(f"❌ خطا در اسکن #{self.scan_count}: {e}")
                logger.error(traceback.format_exc())

                # اگه 5 خطای پشت سرهم → 1 دقیقه صبر بیشتر
                if self.consecutive_errors >= 5:
                    logger.warning("⚠️ 5 خطای پشت سرهم - 60 ثانیه صبر اضافی")
                    time.sleep(60)
                    self.consecutive_errors = 0

            # صبر تا اسکن بعدی
            logger.info(f"⏳ صبر {SCAN_INTERVAL} ثانیه تا اسکن بعدی...")
            time.sleep(SCAN_INTERVAL)

    def _do_single_scan(self):
        """انجام یه دور اسکن کامل"""
        self.scan_count += 1
        self.last_scan_time = time.time()

        logger.info(f"🔍 اسکن #{self.scan_count} شروع شد ({datetime.now().strftime('%H:%M:%S')})")

        # دریافت لیست ارزها
        symbols = self.market.get_usdt_symbols()
        if not symbols:
            logger.warning("هیچ ارزی یافت نشد!")
            return

        total = len(symbols)
        logger.info(f"📊 {total} ارز برای اسکن")

        # مرحله 1: Quick Scan
        candidates = []
        scanned = 0
        for sym_info in symbols:
            if not self.running:
                break

            symbol = sym_info["symbol"]
            base = sym_info["base"]
            is_shitcoin = sym_info.get("is_shitcoin", False)

            # چک cooldown
            if not self.engine.should_send_signal(symbol):
                continue

            scanned += 1
            try:
                result = self.engine.quick_scan(symbol, base, is_shitcoin=is_shitcoin)
                if result:
                    _, _, _, quick_score, direction = result
                    if direction != "NEUTRAL" or quick_score >= 55:
                        candidates.append((result, sym_info))
            except Exception as e:
                logger.debug(f"خطا در quick_scan {symbol}: {e}")

            time.sleep(0.15)

        logger.info(f"✅ Quick scan: {scanned} ارز → {len(candidates)} کاندید")

        # مرحله 2: Deep Scan
        found_signals = []
        for i, (quick_result, sym_info) in enumerate(candidates):
            if not self.running:
                break

            symbol = sym_info["symbol"]
            base = sym_info["base"]
            is_shitcoin = sym_info.get("is_shitcoin", False)

            try:
                signal = self.engine.scan_symbol(symbol, base, is_shitcoin=is_shitcoin)
                if signal and signal.get("direction") != "NEUTRAL":
                    found_signals.append(signal)
                    self.engine.mark_signal_sent(symbol)
            except Exception as e:
                logger.error(f"خطا در deep scan {symbol}: {e}")

            time.sleep(0.3)

        # ارسال سیگنال‌ها
        if found_signals:
            logger.info(f"🎯 {len(found_signals)} سیگنال یافت شد!")
            for signal in found_signals:
                try:
                    msg = self.engine.format_signal_message(signal)
                    if msg:
                        self.telegram_sender(msg)
                        self.signal_count += 1
                        self.last_signal_time = time.time()
                        logger.info(f"📨 سیگنال {signal.get('symbol')} ارسال شد")
                        time.sleep(2)  # فاصله بین ارسال‌ها
                except Exception as e:
                    logger.error(f"خطا در ارسال سیگنال: {e}")
        else:
            logger.info("⚪ هیچ سیگنالی یافت نشد")

        logger.info(
            f"📊 اسکن #{self.scan_count} کامل شد: "
            f"{scanned} ارز → {len(candidates)} کاندید → {len(found_signals)} سیگنال"
        )

    def _health_loop(self):
        """حلقه سلامت - هر 60 ثانیه چک می‌کنه"""
        while self.running:
            time.sleep(60)
            if not self.running:
                break

            try:
                self._check_health()
            except Exception as e:
                logger.error(f"خطا در چک سلامت: {e}")

    def _check_health(self):
        """چک کردن سلامت سیستم"""
        now = time.time()
        time_since_scan = now - self.last_scan_time
        time_since_signal = now - self.last_signal_time

        status = (
            f"💓 Health Check | "
            f"اسکن‌ها: {self.scan_count} | "
            f"سیگنال‌ها: {self.signal_count} | "
            f"خطاها: {self.error_count} | "
            f"آخرین اسکن: {int(time_since_scan // 60)}m ago"
        )
        logger.info(status)

        # هشدار اگه خیلی وقته اسکن نشده
        from config import SCAN_INTERVAL
        if time_since_scan > SCAN_INTERVAL * 3:
            logger.warning(f"⚠️ {int(time_since_scan // 60)} دقیقه از آخرین اسکن گذشته!")
            self._send_alert(f"⚠️ **هشدار سلامت**\n\n"
                           f"⏰ {int(time_since_scan // 60)} دقیقه از آخرین اسکن گذشته!\n"
                           f"🔧 در حال ریکاوری...")

    def _send_alert(self, message):
        """ارسال هشدار مدیریتی"""
        try:
            self.telegram_sender(message)
        except Exception as e:
            logger.error(f"خطا در ارسال هشدار: {e}")
