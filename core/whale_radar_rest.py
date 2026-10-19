# -*- coding: utf-8 -*-
"""
Whale Radar REST - ردیاب نهنگ‌ها با REST API (بدون WebSocket)
برای Render free tier که WebSocket محدود کرده

هر 10 ثانیه recent trades رو از KuCoin می‌گیره و نهنگ‌ها رو تشخیص می‌ده
"""

import time
import logging
import threading
from collections import deque, defaultdict
import requests
from config import WHALE_TX_THRESHOLD, MIN_24H_VOLUME

logger = logging.getLogger(__name__)

KUCOIN_BASE = "https://api.kucoin.com"


class WhaleRadarREST:
    """ردیاب نهنگ‌ها با REST API polling"""

    def __init__(self, on_whale_alert=None):
        self.on_whale_alert = on_whale_alert
        self.running = False
        self.thread = None

        # ارزهای پایش
        self.symbols = []
        self.symbol_map = {}  # BTC-USDT -> BTCUSDT

        # آستانه نهنگ
        self.whale_threshold = WHALE_TX_THRESHOLD

        # آمار
        self.stats = {
            "total_trades": 0,
            "whale_trades": 0,
            "alerts_sent": 0,
            "connected": False,
        }

        # هشدارهای اخیر (جلوگیری از اسپم)
        self.recent_alerts = {}
        self.alert_cooldown = 60  # ثانیه

        # آخرین قیمت
        self.last_prices = {}

    def fetch_symbols(self):
        """دریافت لیست ارزهای پرحجم از KuCoin"""
        try:
            resp = requests.get(f"{KUCOIN_BASE}/api/v1/market/allTickers", timeout=15)
            data = resp.json()
            if data.get("code") != "200000":
                return []

            symbols = []
            symbol_map = {}
            for item in data["data"]["ticker"]:
                sym = item.get("symbol", "")
                if not sym.endswith("-USDT"):
                    continue
                base = sym.replace("-USDT", "")
                if base in ["USDC", "BUSD", "TUSD", "DAI", "FDUSD"]:
                    continue

                vol = float(item.get("volValue", 0))
                if vol < MIN_24H_VOLUME:
                    continue

                symbols.append(sym)
                symbol_map[sym] = base + "USDT"

            # 20 ارز برتر
            self.symbols = symbols[:20]
            self.symbol_map = {s: symbol_map[s] for s in self.symbols}

            logger.info(f"🐋 Whale Radar REST: {len(self.symbols)} ارز آماده")
            self.stats["connected"] = True
            return self.symbols
        except Exception as e:
            logger.error(f"خطا در دریافت لیست ارزها: {e}")
            return []

    def fetch_trades(self, symbol):
        """دریافت تریدهای اخیر از KuCoin"""
        try:
            resp = requests.get(
                f"{KUCOIN_BASE}/api/v1/market/histories",
                params={"symbol": symbol, "limit": 100},
                timeout=10
            )
            data = resp.json()
            if data.get("code") != "200000":
                return []
            return data.get("data", [])
        except Exception as e:
            logger.debug(f"خطا در دریافت ترید {symbol}: {e}")
            return []

    def process_trade(self, symbol, trade):
        """بررسی یه ترید و تشخیص نهنگ"""
        try:
            price = float(trade.get("price", 0))
            size = float(trade.get("size", 0))
            side = trade.get("side", "")  # "buy" or "sell"

            if price == 0 or size == 0:
                return

            notional = price * size
            self.stats["total_trades"] += 1

            # آستانه نهنگ
            threshold = self.whale_threshold

            if notional >= threshold:
                self.stats["whale_trades"] += 1
                direction = "buy" if side == "buy" else "sell"

                # چک کردن cooldown
                key = (symbol, direction)
                now = time.time()
                if key in self.recent_alerts:
                    if now - self.recent_alerts[key] < self.alert_cooldown:
                        return

                self.recent_alerts[key] = now
                self.stats["alerts_sent"] += 1

                # فرمت alert
                base = self.symbol_map.get(symbol, symbol)
                alert = {
                    "type": "SINGLE_WHALE",
                    "symbol": symbol,
                    "base": base,
                    "direction": direction,
                    "direction_farsi": "خرید" if direction == "buy" else "فروش",
                    "price": price,
                    "size": size,
                    "value_usdt": notional,
                    "time": now,
                    "time_str": time.strftime("%H:%M:%S"),
                    "exchange": "KuCoin",
                }

                if self.on_whale_alert:
                    self.on_whale_alert(alert)

                logger.info(
                    f"🐋 نهنگ! {base} {direction} {notional/1000:.0f}K USDT @ {price:.4f}"
                )
        except Exception as e:
            logger.debug(f"خطا در پردازش ترید: {e}")

    def scan_loop(self):
        """حلقه اصلی اسکن"""
        logger.info("🐋 Whale Radar REST شروع شد")

        while self.running:
            try:
                if not self.symbols:
                    self.fetch_symbols()
                    time.sleep(5)
                    continue

                for symbol in self.symbols:
                    if not self.running:
                        break

                    trades = self.fetch_trades(symbol)
                    for trade in trades:
                        self.process_trade(symbol, trade)

                    # کوتاه خواب بین هر ارز
                    time.sleep(0.5)

                # خواب بین هر دور
                time.sleep(10)

            except Exception as e:
                logger.error(f"خطا در حلقه Whale Radar: {e}")
                time.sleep(5)

        logger.info("🐋 Whale Radar REST متوقف شد")

    def start(self):
        """شروع Whale Radar"""
        if self.running:
            return

        self.running = True
        self.fetch_symbols()
        self.thread = threading.Thread(target=self.scan_loop, daemon=True)
        self.thread.start()
        logger.info("🐋 Whale Radar REST استارت خورد")

    def stop(self):
        """توقف Whale Radar"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def get_stats(self):
        """آمار"""
        return {
            "running": self.running,
            "symbols_count": len(self.symbols),
            "total_trades": self.stats["total_trades"],
            "whale_trades": self.stats["whale_trades"],
            "alerts_sent": self.stats["alerts_sent"],
            "connected": self.stats["connected"],
        }

    def format_whale_alert(self, alert):
        """فرمت هشدار برای تلگرام"""
        emoji = "🟢" if alert.get("direction") == "buy" else "🔴"
        base = alert.get("base", "")
        value = alert.get("value_usdt", 0)
        price = alert.get("price", 0)
        direction = alert.get("direction_farsi", "")
        time_str = alert.get("time_str", "")

        if value >= 1_000_000:
            size_str = f"{value/1_000_000:.1f}M"
        else:
            size_str = f"{value/1000:.0f}K"

        return (
            f"{emoji} **نهنگ {base}**\n\n"
            f"💰 {direction}: {size_str} USDT\n"
            f"💵 قیمت: {price:.4f}\n"
            f"🏢 صرافی: KuCoin\n"
            f"⏰ {time_str}"
        )
