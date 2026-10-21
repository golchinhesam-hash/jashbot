# -*- coding: utf-8 -*-
"""
بات تلگرام برای ارسال سیگنال‌های کریپتو
دستورات:
/start - شروع بات و اسکنر
/status - وضعیت بات
/scan - اسکن دستی بازار
/radar - وضعیت Whale Radar لحظه‌ای
/last - آخرین سیگنال‌ها
/help - راهنما
"""

import logging
import time
import threading
import config
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from core.signal_engine import SignalEngine
from core.market_data import MarketData
from core.whale_radar import WhaleRadar
from core.whale_radar_rest import WhaleRadarREST
from core.signal_engine import format_persian_time, format_persian_datetime_short

logger = logging.getLogger(__name__)


class TelegramBot:
    """بات تلگرام برای سیگنال کریپتو"""

    def __init__(self):
        self.market = MarketData()
        self.engine = SignalEngine(self.market)
        # روی Render از REST استفاده کن (WebSocket محدوده)
        self.radar = WhaleRadarREST(on_whale_alert=self._on_whale_alert)
        self.app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        self.running = False
        self.last_signals = []
        self.whale_alerts = []  # لیست آخرین هشدارهای نهنگ
        self.active_positions = []  # پوزیشن‌های فعال با تایمر
        self.chat_id = None
        self._setup_handlers()

    def add_position(self, signal):
        """اضافه کردن پوزیشن فعال برای ردیابی زمان"""
        import config
        now = time.time()
        exit_ts = now + (config.MAX_POSITION_DURATION_HOURS * 3600)
        warning_ts = exit_ts - (config.POSITION_EXPIRY_WARNING_MINUTES * 60)
        position = {
            'symbol': signal.get('symbol'),
            'direction': signal.get('direction'),
            'entry': signal.get('entry'),
            'entry_time': now,
            'exit_time': exit_ts,
            'warning_time': warning_ts,
            'entry_persian': format_persian_time(now),
            'exit_persian': format_persian_time(exit_ts),
            'warning_persian': format_persian_time(warning_ts),
            'warning_sent': False,
            'expired': False,
        }
        self.active_positions.append(position)
        logger.info(f"پوزیشن اضافه شد: {position['symbol']} {position['direction']} - خروج: {config.MAX_POSITION_DURATION_HOURS} ساعت")

    def check_position_expiry(self):
        """چک کردن پوزیشن‌های فعال و ارسال هشدار"""
        now = time.time()
        for pos in self.active_positions:
            if pos['expired']:
                continue
            
            # هشدار 30 دقیقه قبل
            if not pos['warning_sent'] and now >= pos['warning_time']:
                pos['warning_sent'] = True
                self._send_expiry_warning(pos)
            
            # زمان تموم شد
            if now >= pos['exit_time']:
                pos['expired'] = True
                self._send_expiry_alert(pos)
        
        # پاک کردن پوزیشن‌های expired
        self.active_positions = [p for p in self.active_positions if not p['expired']]

    def _send_expiry_warning(self, position):
        """هشدار 30 دقیقه قبل از اتمام زمان"""
        if not self.chat_id:
            return
        exit_short = format_persian_datetime_short(position['exit_time'])
        msg = (
            f"⚠️ **هشدار زمان پوزیشن**

"
            f"{position['symbol']} - {position['direction']}
"
            f"ورود: {position['entry']:.4f}
"
            f"زمان خروج: {exit_short}

"
            f"⏰ **30 دقیقه دیگه زمان تموم میشه!**
"
            f"🔴 آماده باش برای بستن پوزیشن

"
            f"💡 یا TP بگیر یا استاپ رو به سود منتقل کن"
        )
        try:
            import asyncio
            asyncio.create_task(self.app.bot.send_message(self.chat_id, msg, parse_mode='Markdown'))
        except:
            pass

    def _send_expiry_alert(self, position):
        """هشدار اتمام زمان پوزیشن"""
        if not self.chat_id:
            return
        entry_short = format_persian_datetime_short(position['entry_time'])
        exit_short = format_persian_datetime_short(position['exit_time'])
        msg = (
            f"🔴 **زمان پوزیشن تموم شد!**

"
            f"{position['symbol']} - {position['direction']}
"
            f"ورود: {position['entry']:.4f}
"
            f"از: {entry_short} تا: {exit_short}

"
            f"⏰ **حداکثر زمان ({config.MAX_POSITION_DURATION_HOURS} ساعت) تموم شد**

"
            f"⚠️ **پوزیشن رو ببند!**
"
            f"حتی اگه ضرری - ریسک نکن

"
            f"📊 بعدش /scan بزن برای سیگنال جدید"
        )
        try:
            import asyncio
            asyncio.create_task(self.app.bot.send_message(self.chat_id, msg, parse_mode='Markdown'))
        except:
            pass

    def _setup_handlers(self):
        """ثبت دستورات"""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("scan", self.cmd_scan))
        self.app.add_handler(CommandHandler("radar", self.cmd_radar))
        self.app.add_handler(CommandHandler("last", self.cmd_last))
        self.app.add_handler(CommandHandler("help", self.cmd_help))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /start - ذخیره چت آیدی و شروع بات"""
        chat_id = update.effective_chat.id
        first_name = update.effective_user.first_name

        # ذخیره چت آیدی
        self.chat_id = chat_id
        config.TELEGRAM_CHAT_ID = chat_id
        if not config.ADMIN_IDS:
            config.ADMIN_IDS = [chat_id]

        logger.info(f"کاربر {first_name} (ID: {chat_id}) بات رو استارت زد")

        msg = (
            f"🤖 ربات سیگنال کریپتو + Whale Radar\n\n"
            f"سلام {first_name}! چت آیدی شما ثبت شد: `{chat_id}`\n\n"
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
            f"/help - راهنما\n\n"
            f"⚡ Whale Radar فعال شد - هشدار نهنگ‌ها رو لحظه‌ای می‌گیری\n"
            f"⚡ سریع‌تر از کنال‌های هشدار نهنگ"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

        # شروع اسکنر خودکار
        if not self.running:
            self.start_scanner_loop()

        # شروع Whale Radar
        if not self.radar.running:
            self.radar.start()

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /status"""
        status = "✅ فعال" if self.running else "❌ غیرفعال"
        radar_stats = self.radar.get_stats()
        binance_stats = radar_stats.get("binance", {})
        bybit_stats = radar_stats.get("bybit", {})

        msg = (
            f"📊 وضعیت بات\n\n"
            f"اسکنر دوره‌ای: {status}\n"
            f"فاصله اسکن: {config.SCAN_INTERVAL} ثانیه\n"
            f"تعداد سیگنال ارسالی: {len(self.last_signals)}\n"
            f"چت آیدی: {self.chat_id or config.TELEGRAM_CHAT_ID}\n\n"
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
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_radar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /radar - وضعیت لحظه‌ای Whale Radar"""
        stats = self.radar.get_stats()
        if not self.radar.running:
            await update.message.reply_text("❌ Whale Radar فعال نیست. /start بزنید.")
            return

        msg = (
            f"🐋 Whale Radar - وضعیت لحظه‌ای\n\n"
            f"🔗 Binance: {'✅ متصل' if stats.get('binance', {}).get('connected') else '❌ قطع'}\n"
            f"🔗 Bybit: {'✅ متصل' if stats.get('bybit', {}).get('connected') else '❌ قطع'}\n"
            f"📊 ارزهای پایش: {stats.get('symbols_count', 0)}\n"
            f"⚡ کل هشدارها: {stats.get('total_alerts', 0)}\n\n"
            f"آخرین هشدارها:\n"
        )

        if self.whale_alerts:
            for a in self.whale_alerts[-5:]:
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
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اسکن دستی بازار"""
        chat_id = update.effective_chat.id

        # فقط ادمین‌ها
        if config.ADMIN_IDS and chat_id not in config.ADMIN_IDS:
            await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
            return

        await update.message.reply_text("🔍 شروع اسکن بازار... لطفاً صبر کنید.")

        # اجرای اسکن در thread جدا
        def do_scan():
            found = self.run_market_scan()
            if found:
                for signal in found:
                    msg = self.engine.format_signal_message(signal)
                    if msg:
                        context.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
            else:
                context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ هیچ سیگنال معتبری در حال حاضر یافت نشد.",
                    parse_mode="Markdown"
                )

        thread = threading.Thread(target=do_scan)
        thread.start()

    async def cmd_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش آخرین سیگنال‌ها"""
        if not self.last_signals:
            await update.message.reply_text("📭 هنوز سیگنالی ارسال نشده.")
            return

        msg = "📋 **آخرین سیگنال‌ها:**\n\n"
        for s in self.last_signals[-5:]:
            direction_emoji = "🟢" if s.get("direction") == "LONG" else "🔴"
            msg += (
                f"{direction_emoji} **{s.get('base', s.get('symbol', ''))}** "
                f"- {s.get('direction')} "
                f"(امتیاز: {s.get('score', 0):.0f})\n"
                f"   ورود: {s.get('entry', 0):.4f}\n\n"
            )

        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /help"""
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
        await update.message.reply_text(msg, parse_mode="Markdown")

    def run_market_scan(self, progress_callback=None):
        """
        اسکن کامل بازار - دو مرحله‌ای:
        1. Quick scan: فقط klines 1h برای همه ارزها (سریع)
        2. Deep scan: اسکن کامل فقط برای ارزهای امیدوارکننده
        
        progress_callback: تابع اختیاری برای ارسال پیشرفت (مثلا به تلگرام)
        """
        logger.info("شروع اسکن بازار (دو مرحله‌ای)...")
        
        if progress_callback:
            progress_callback("📡 مرحله ۱: دریافت لیست ارزها...")

        symbols = self.market.get_usdt_symbols()

        if not symbols:
            logger.warning("هیچ ارزی یافت نشد!")
            return []

        total = len(symbols)
        logger.info(f"تعداد {total} ارز برای quick scan")
        
        if progress_callback:
            progress_callback(f"🔍 شروع Quick Scan: {total} ارز...")

        # === مرحله 1: Quick Scan (سریع) ===
        candidates = []
        scan_count = 0
        error_count = 0
        last_progress = 0
        for sym_info in symbols:
            symbol = sym_info["symbol"]
            base = sym_info["base"]
            is_shitcoin = sym_info.get("is_shitcoin", False)

            # بررسی cooldown
            if not self.engine.should_send_signal(symbol):
                continue

            scan_count += 1
            
            # ارسال پیشرفت هر 50 ارز
            if progress_callback and scan_count % 50 == 0:
                pct = scan_count * 100 // total
                progress_callback(f"⏳ Quick Scan: {scan_count}/{total} ({pct}%) - {len(candidates)} کاندید")

            try:
                result = self.engine.quick_scan(symbol, base, is_shitcoin=is_shitcoin)
                if result:
                    _, _, _, quick_score, direction = result
                    # فقط ارزهایی که امتیاز سریع بالای 55 دارن یا جهت مشخص دارن
                    if direction != "NEUTRAL" or quick_score >= 55:
                        candidates.append((result, sym_info))
            except Exception as e:
                logger.debug(f"خطا در quick_scan {symbol}: {e}")
                error_count += 1

            # مکث کوتاه بین ارزها
            time.sleep(0.15)

        logger.info(f"Quick scan کامل شد: {scan_count} ارز بررسی شد، {len(candidates)} کاندید برای deep scan ({error_count} خطا)")
        
        if progress_callback:
            progress_callback(f"✅ Quick Scan کامل شد: {len(candidates)} کاندید از {scan_count} ارز\n🔬 شروع Deep Scan...")

        # === مرحله 2: Deep Scan (فقط کاندیدها) ===
        found_signals = []
        neutral_picks = []  # ارزهای امتیاز بالا ولی NEUTRAL
        for i, (quick_result, sym_info) in enumerate(candidates):
            symbol = sym_info["symbol"]
            base = sym_info["base"]
            is_shitcoin = sym_info.get("is_shitcoin", False)
            _, _, _, quick_score, direction_hint = quick_result

            tag = " 🐕" if is_shitcoin else ""
            logger.info(f"Deep scan {i+1}/{len(candidates)}: {symbol}{tag} (quick_score: {quick_score:.0f}, hint: {direction_hint})")
            
            if progress_callback and (i+1) % 10 == 0:
                progress_callback(f"🔬 Deep Scan: {i+1}/{len(candidates)} - {len(found_signals)} سیگنال")

            try:
                signal = self.engine.scan_symbol(symbol, base, is_shitcoin=is_shitcoin)

                if signal and signal.get("direction") != "NEUTRAL":
                    found_signals.append(signal)
                    self.engine.mark_signal_sent(symbol)
                    self.last_signals.append(signal)

                    # نگهداری فقط 20 سیگنال اخیر
                    if len(self.last_signals) > 20:
                        self.last_signals = self.last_signals[-20:]

                    # ارسال سیگنال فوری
                    msg = self.engine.format_signal_message(signal)
                    if msg:
                        self._send_to_channel(msg)
                elif signal and signal.get("score", 0) >= 50:
                    # نگه داشتن ارزهای امتیاز بالا ولی خنثی برای watch list
                    neutral_picks.append(signal)
            except Exception as e:
                logger.error(f"خطا در deep scan {symbol}: {e}")

            # مکث بین deep scan (کمتر چون تعداد کمتره)
            time.sleep(0.3)

        logger.info(f"اسکن کامل شد. {len(candidates)} کاندید بررسی شد. {len(found_signals)} سیگنال یافت شد.")
        
        if progress_callback:
            progress_callback(f"✅ اسکن کامل شد!\n📊 {scan_count} ارز بررسی شد\n🎯 {len(candidates)} کاندید → {len(found_signals)} سیگنال")

        # اگه سیگنال پیدا نشد، top picks رو بفرست
        if not found_signals and neutral_picks:
            neutral_picks.sort(key=lambda x: x.get("score", 0), reverse=True)
            self._send_top_picks(neutral_picks[:5])

        return found_signals

    def _send_top_picks(self, picks):
        """ارسال بهترین ارزهای خنثی به عنوان watch list"""
        if not picks:
            return
        msg = "📊 Top Picks - فرصت‌های تحت نظر\n(سیگنال کامل نیست ولی امتیاز بالایی دارن)\n\n"
        for i, s in enumerate(picks, 1):
            emoji = "📈" if s.get("score", 0) >= 60 else "➡️"
            msg += (
                f"{i}. {emoji} {s.get('base', s.get('symbol', ''))}\n"
                f"   امتیاز: {s.get('score', 0):.0f}/100\n"
            )
            reasons = s.get("reasons", [])
            if reasons:
                for r in reasons[:3]:
                    msg += f"   • {r}\n"
            msg += "\n"

        msg += "💡 این ارزها سیگنال کامل ندارن ولی نشونه‌های خوبی دارن. تحت نظر بگیر."
        self._send_to_channel(msg)

    def _on_whale_alert(self, alert):
        """کال‌بک هشدار نهنگ از Whale Radar"""
        logger.info(f"🐳 هشدار نهنگ دریافت شد: {alert.get('symbol')} {alert.get('direction')}")
        self.whale_alerts.append(alert)
        if len(self.whale_alerts) > 50:
            self.whale_alerts = self.whale_alerts[-50:]

        msg = self.radar.format_whale_alert(alert)
        self._send_to_channel(msg)

    def _send_to_channel(self, message):
        """ارسال پیام به تلگرام"""
        chat_id = self.chat_id or config.TELEGRAM_CHAT_ID
        if not chat_id:
            logger.warning("چت آیدی تنظیم نشده. ابتدا /start بزنید.")
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            resp = requests.post(url, data=data, timeout=15)
            if resp.status_code == 200:
                logger.info("سیگنال ارسال شد")
            else:
                logger.error(f"خطا در ارسال: {resp.text}")
        except Exception as e:
            logger.error(f"خطا در ارسال تلگرام: {e}")

    def start_scanner_loop(self):
        """شروع حلقه اسکن خودکار"""
        if self.running:
            return
        self.running = True

        def loop():
            while self.running:
                try:
                    self.run_market_scan()
                except Exception as e:
                    logger.error(f"خطا در حلقه اسکن: {e}")

                # صبر تا اسکن بعدی
                time.sleep(config.SCAN_INTERVAL)

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        logger.info(f"اسکنر خودکار شروع شد (هر {config.SCAN_INTERVAL} ثانیه)")

    def run(self):
        """اجرای بات - منتظر /start می‌مونه"""
        logger.info("شروع بات تلگرام...")
        logger.info("برای فعال شدن، در تلگرام /start بزنید")

        # شروع polling - اسکنر بعد از /start شعیت می‌کنه
        self.app.run_polling()
