# -*- coding: utf-8 -*-
"""
Whale Radar - ردیاب لحظه‌ای نهنگ‌ها (Multi-Exchange)
از طریق WebSocket به Binance و Bybit وصل میشه و تریدهای بزرگ رو در لحظه تشخیص میده

مزیت compared to کانال تلگرام VolumeTrackingAlerts:
- کانال تلگرام: نهنگ ترید -> پردازش TapeDelta -> پست تلگرام -> شما می‌بینی (تأخیر 1-5 دقیقه)
- این ماژول: نهنگ ترید -> تشخیص لحظه‌ای -> هشدار تلگرام (تأخیر < 2 ثانیه)

منابع داده:
1. Binance aggTrade WebSocket - هر ترید رو لحظه‌ای
2. Bybit trade WebSocket - هر ترید رو لحظه‌ای
3. ترکیب داده‌های هر دو صرافی برای تشخیص دقیق‌تر

دو نوع هشدار:
A) SINGLE_WHALE - یه ترید خیلی بزرگ (نهنگ تکی)
B) WHALE_CLUSTER - چند ترید بزرگ پشت سر هم در 60 ثانیه
"""

import json
import time
import logging
import threading
from collections import deque, defaultdict
import websocket
import requests
from config import (
    BINANCE_BASE_URL,
    WHALE_TX_THRESHOLD,
    WHALE_SIGNAL_THRESHOLD,
    MIN_24H_VOLUME,
    SCAN_INTERVAL,
)

logger = logging.getLogger(__name__)

# صرافی‌های پشتیبانی شده
EXCHANGES = {
    "binance": {
        "name": "Binance",
        "ws_url": "wss://stream.binance.com:9443/stream",
        "rest_url": "https://api.binance.com",
    },
    "bybit": {
        "name": "Bybit",
        "ws_url": "wss://stream.bybit.com/v5/public/spot",
        "rest_url": "https://api.bybit.com",
    },
}


class WhaleRadar:
    """ردیاب لحظه‌ای نهنگ‌ها - چند صرافی"""

    def __init__(self, on_whale_alert=None):
        self.on_whale_alert = on_whale_alert
        self.ws_connections = {}  # exchange -> ws
        self.running = False
        self.connected = {}

        # پنجره تجمیع
        self.whale_trades_window = defaultdict(list)
        self.window_seconds = 60

        # آمار هر صرافی
        self.stats = {
            exchange: {
                "total_trades": 0,
                "whale_trades": 0,
                "alerts_sent": 0,
                "connected": False,
            }
            for exchange in EXCHANGES
        }

        # آمار کلی
        self.total_alerts_sent = 0

        # ارزها
        self.symbols = []
        self.symbols_bybit = []

        # آستانه‌ها
        self.whale_thresholds = {}
        self.single_whale_threshold = {}  # آستانه تک‌ترید بزرگ

        # آخرین قیمت‌ها
        self.last_prices = {}

        # میانگین حجم ترید
        self.avg_trade_sizes = defaultdict(lambda: deque(maxlen=1000))

        # هشدارهای اخیر برای جلوگیری از اسپم
        self.recent_alerts = {}  # (symbol, direction) -> last_alert_time
        self.alert_cooldown = 30  # حداقل 30 ثانیه بین هشدار برای همان ارز+جهت

    def fetch_symbols(self):
        """دریافت لیست ارزهای USDT با حجم بالا از Binance"""
        try:
            resp = requests.get(f"{BINANCE_BASE_URL}/api/v3/ticker/24hr", timeout=15)
            data = resp.json()
            symbols = []
            for item in data:
                symbol = item.get("symbol", "")
                if not symbol.endswith("USDT"):
                    continue
                base = symbol.replace("USDT", "")
                skip = ["UP", "DOWN", "BULL", "BEAR"]
                if any(base.endswith(s) for s in skip):
                    continue
                if base in ["USDC", "BUSD", "TUSD", "DAI", "FDUSD"]:
                    continue

                quote_volume = float(item.get("quoteVolume", 0))
                if quote_volume < MIN_24H_VOLUME:
                    continue

                symbols.append(symbol)

            self.symbols = symbols[:15]  # 15 ارز برتر Binance
            self.symbols_bybit = [s.lower() for s in self.symbols]

            logger.info(f"تعداد {len(self.symbols)} ارز برای Whale Radar آماده شد")

            for sym in self.symbols:
                self.whale_thresholds[sym] = WHALE_TX_THRESHOLD
                self.single_whale_threshold[sym] = WHALE_TX_THRESHOLD * 3

            return symbols
        except Exception as e:
            logger.error(f"خطا در دریافت لیست ارزها: {e}")
            return []

    def adjust_thresholds(self):
        """تنظیم آستانه داینامیک"""
        for symbol, sizes in self.avg_trade_sizes.items():
            if len(sizes) < 100:
                continue
            sorted_sizes = sorted(sizes)
            p95 = sorted_sizes[int(len(sorted_sizes) * 0.95)]
            p99 = sorted_sizes[int(len(sorted_sizes) * 0.99)]

            self.whale_thresholds[symbol] = max(
                self.whale_thresholds.get(symbol, WHALE_TX_THRESHOLD),
                p95 * 3
            )
            self.single_whale_threshold[symbol] = max(
                self.single_whale_threshold.get(symbol, WHALE_TX_THRESHOLD * 3),
                p99 * 2
            )

    # ===================== Binance =====================
    def on_message_binance(self, ws, message):
        """پردازش تریدهای Binance (combined stream)"""
        try:
            data = json.loads(message)
            # Combined stream: {"stream": "btcusdt@aggTrade", "data": {...}}
            if "data" in data:
                trade_data = data["data"]
            else:
                trade_data = data

            symbol = trade_data.get("s", "")
            price = float(trade_data.get("p", 0))
            qty = float(trade_data.get("q", 0))
            trade_time = trade_data.get("T", 0)
            is_maker = trade_data.get("m", False)

            if not symbol or price == 0:
                return

            self._process_trade(symbol, price, qty, trade_time, is_maker, "binance")
        except Exception as e:
            logger.error(f"خطا Binance WS: {e}")

    # ===================== Bybit =====================
    def on_message_bybit(self, ws, message):
        """پردازش تریدهای Bybit v5 publicTrade"""
        try:
            data = json.loads(message)
            topic = data.get("topic", "")

            if not topic.startswith("publicTrade."):
                return

            for trade in data.get("data", []):
                # Bybit v5 publicTrade fields:
                # T = timestamp (ms), S = symbol, s = side ("Buy"/"Sell"),
                # p = price, v = quantity
                symbol = trade.get("S", "")
                price = float(trade.get("p", 0))
                qty = float(trade.get("v", 0))
                trade_time = int(trade.get("T", 0))
                side = trade.get("s", "")  # "Buy" or "Sell"

                if not symbol or price == 0:
                    continue

                # تبدیل symbol Bybit به فرمت Binance
                if not symbol.endswith("USDT"):
                    symbol = symbol + "USDT"

                # Bybit: "Buy" = buyer is taker => market buy (is_maker=False)
                # Bybit: "Sell" = seller is taker => market sell (is_maker=True)
                is_maker = (side == "Sell")

                self._process_trade(symbol, price, qty, trade_time, is_maker, "bybit")
        except Exception as e:
            logger.error(f"خطا Bybit WS: {e}")

    def _process_trade(self, symbol, price, qty, trade_time, is_maker, exchange):
        """پردازش مرکزی هر ترید از هر صرافی"""
        # نرمال‌سازی کلید صرافی
        exchange_key = exchange.lower() if isinstance(exchange, str) else "unknown"
        if exchange_key not in self.stats:
            self.stats[exchange_key] = {
                "total_trades": 0, "whale_trades": 0,
                "alerts_sent": 0, "connected": False,
            }

        self.stats[exchange_key]["total_trades"] += 1

        value = price * qty
        self.last_prices[symbol] = price
        self.avg_trade_sizes[symbol].append(value)

        # تشخیص نهنگ
        threshold = self.whale_thresholds.get(symbol, WHALE_TX_THRESHOLD)
        single_threshold = self.single_whale_threshold.get(symbol, WHALE_TX_THRESHOLD * 3)

        if value < threshold:
            return

        # این یه ترید نهنگ هست!
        self.stats[exchange_key]["whale_trades"] += 1
        direction = "sell" if is_maker else "buy"

        logger.info(
            f"🐳 نهنگ {exchange} {symbol} {direction}: "
            f"{value/1e6:.2f}M USDT @ {price}"
        )

        # === هشدار نوع A: تک‌تراد خیلی بزرگ ===
        if value >= single_threshold:
            self._trigger_single_whale_alert(symbol, price, qty, value, direction, exchange, trade_time)

        # === هشدار نوع B: تجمع نهنگ ===
        self.whale_trades_window[symbol].append({
            "time": trade_time,
            "price": price,
            "qty": qty,
            "value": value,
            "direction": direction,
            "exchange": exchange,
        })

        # پاکسازی پنجره
        cutoff = trade_time - (self.window_seconds * 1000)
        self.whale_trades_window[symbol] = [
            t for t in self.whale_trades_window[symbol]
            if t["time"] >= cutoff
        ]

        self._check_whale_cluster(symbol, price, direction, value, exchange, trade_time)

    def _trigger_single_whale_alert(self, symbol, price, qty, value, direction, exchange, trade_time):
        """هشدار تک‌ترید بزرگ"""
        key = (symbol, "single")
        now = time.time()
        if now - self.recent_alerts.get(key, 0) < self.alert_cooldown:
            return
        self.recent_alerts[key] = now

        alert = {
            "type": "SINGLE_WHALE",
            "symbol": symbol,
            "base": symbol.replace("USDT", ""),
            "direction": direction,
            "direction_farsi": "خرید" if direction == "buy" else "فروش",
            "value_usdt": value,
            "price": price,
            "qty": qty,
            "exchange": exchange,
            "timestamp": trade_time,
            "time_str": time.strftime("%H:%M:%S"),
        }

        self.total_alerts_sent += 1
        ex_key = exchange.lower() if isinstance(exchange, str) else "unknown"
        if ex_key in self.stats:
            self.stats[ex_key]["alerts_sent"] += 1

        logger.info(f"🚨 تک‌نهنگ {exchange} {symbol} {direction}: {value/1e6:.2f}M!")

        if self.on_whale_alert:
            self.on_whale_alert(alert)

    def _check_whale_cluster(self, symbol, price, direction, value, exchange, trade_time):
        """بررسی تجمع نهنگ‌ها"""
        key = (symbol, direction)
        now = time.time()
        if now - self.recent_alerts.get(key, 0) < self.alert_cooldown:
            return

        window = self.whale_trades_window.get(symbol, [])
        if len(window) < WHALE_SIGNAL_THRESHOLD:
            return

        same_dir = [t for t in window if t["direction"] == direction]
        opposite_dir = [t for t in window if t["direction"] != direction]

        if len(same_dir) < WHALE_SIGNAL_THRESHOLD:
            return

        self.recent_alerts[key] = now

        total_value = sum(t["value"] for t in same_dir)
        avg_price = sum(t["price"] for t in same_dir) / len(same_dir)

        # لیست صرافی‌های درگیر
        exchanges_involved = list(set(t["exchange"] for t in same_dir))

        alert = {
            "type": "WHALE_CLUSTER",
            "symbol": symbol,
            "base": symbol.replace("USDT", ""),
            "direction": direction,
            "direction_farsi": "خرید" if direction == "buy" else "فروش",
            "cluster_count": len(same_dir),
            "total_value_usdt": total_value,
            "avg_price": avg_price,
            "current_price": price,
            "window_seconds": self.window_seconds,
            "largest_trade": max(t["value"] for t in same_dir),
            "opposite_count": len(opposite_dir),
            "exchanges": exchanges_involved,
            "timestamp": trade_time,
            "time_str": time.strftime("%H:%M:%S"),
        }

        self.total_alerts_sent += 1
        ex_key = exchange.lower() if isinstance(exchange, str) else "unknown"
        if ex_key in self.stats:
            self.stats[ex_key]["alerts_sent"] += 1

        logger.info(
            f"🐳🚨 تجمع نهنگ {symbol} {direction}: {len(same_dir)} ترید، "
            f"مجموع {total_value/1e6:.1f}M از {exchanges_involved}"
        )

        if self.on_whale_alert:
            self.on_whale_alert(alert)

    # ===================== WebSocket Handlers =====================
    def on_open_binance(self, ws):
        logger.info("✅ Binance WebSocket متصل شد")
        self.connected["binance"] = True
        self.stats["binance"]["connected"] = True

    def on_open_bybit(self, ws):
        logger.info("✅ Bybit WebSocket متصل شد")
        self.connected["bybit"] = True
        self.stats["bybit"]["connected"] = True

    def on_error_generic(self, ws, error, exchange="binance"):
        ex_key = exchange.lower() if isinstance(exchange, str) else "unknown"
        logger.error(f"خطای WebSocket {exchange}: {error}")
        self.connected[ex_key] = False
        if ex_key in self.stats:
            self.stats[ex_key]["connected"] = False

    def on_close_generic(self, ws, close_status, close_msg, exchange="binance"):
        ex_key = exchange.lower() if isinstance(exchange, str) else "unknown"
        logger.warning(f"WebSocket {exchange} بسته شد: {close_status}")
        self.connected[ex_key] = False
        if ex_key in self.stats:
            self.stats[ex_key]["connected"] = False

    # ===================== Stream URLs =====================
    def build_binance_url(self):
        """URL برای Binance WebSocket"""
        streams = [f"{sym.lower()}@aggTrade" for sym in self.symbols]
        stream_str = "/".join(streams)
        return f"wss://stream.binance.com:9443/stream?streams={stream_str}"

    def build_bybit_url(self):
        """URL برای Bybit WebSocket"""
        # Bybit از subscribe message استفاده می‌کنه، نه query param
        return "wss://stream.bybit.com/v5/public/spot"

    def build_bybit_subscribe(self):
        """پیام subscribe برای Bybit"""
        topics = [f"publicTrade.{sym}" for sym in self.symbols_bybit]
        return json.dumps({"op": "subscribe", "args": topics})

    # ===================== Start / Stop =====================
    def start(self):
        """شروع Whale Radar - هر دو صرافی"""
        if self.running:
            return

        self.fetch_symbols()
        if not self.symbols:
            logger.error("هیچ ارزی برای پایش یافت نشد")
            return

        self.running = True

        # شروع Binance WebSocket
        binance_thread = threading.Thread(target=self._run_binance_ws, daemon=True)
        binance_thread.start()

        # شروع Bybit WebSocket
        bybit_thread = threading.Thread(target=self._run_bybit_ws, daemon=True)
        bybit_thread.start()

        # thread برای تنظیم آستانه‌های داینامیک
        threshold_thread = threading.Thread(target=self._threshold_loop, daemon=True)
        threshold_thread.start()

        logger.info(f"Whale Radar شروع شد - {len(self.symbols)} ارز - Binance + Bybit")

    def _run_binance_ws(self):
        """اجرای WebSocket Binance با retry"""
        url = self.build_binance_url()
        retry = 0

        while self.running:
            try:
                self.ws_connections["binance"] = websocket.WebSocketApp(
                    url,
                    on_open=self.on_open_binance,
                    on_message=self.on_message_binance,
                    on_error=lambda ws, e: self.on_error_generic(ws, e, "binance"),
                    on_close=lambda ws, s, m: self.on_close_generic(ws, s, m, "binance"),
                )
                self.ws_connections["binance"].run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                )
            except Exception as e:
                logger.error(f"خطای Binance WS: {e}")

            if not self.running:
                break
            retry += 1
            logger.info(f"تلاش مجدد Binance WS در 5 ثانیه... ({retry})")
            time.sleep(5)

    def _run_bybit_ws(self):
        """اجرای WebSocket Bybit با retry"""
        url = self.build_bybit_url()
        subscribe_msg = self.build_bybit_subscribe()
        retry = 0

        while self.running:
            try:
                ws = websocket.WebSocketApp(
                    url,
                    on_open=lambda w: self._bybit_on_open(w, subscribe_msg),
                    on_message=self.on_message_bybit,
                    on_error=lambda ws, e: self.on_error_generic(ws, e, "bybit"),
                    on_close=lambda ws, s, m: self.on_close_generic(ws, s, m, "bybit"),
                )
                self.ws_connections["bybit"] = ws
                ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                )
            except Exception as e:
                logger.error(f"خطای Bybit WS: {e}")

            if not self.running:
                break
            retry += 1
            logger.info(f"تلاش مجدد Bybit WS در 5 ثانیه... ({retry})")
            time.sleep(5)

    def _bybit_on_open(self, ws, subscribe_msg):
        """Bybit نیاز به subscribe message داره"""
        logger.info("✅ Bybit WebSocket متصل شد - ارسال subscribe")
        self.connected["bybit"] = True
        self.stats["bybit"]["connected"] = True
        ws.send(subscribe_msg)

    def _threshold_loop(self):
        """Loop برای تنظیم آستانه‌های داینامیک"""
        while self.running:
            time.sleep(60)  # هر دقیقه
            try:
                self.adjust_thresholds()
            except Exception as e:
                logger.error(f"خطا در تنظیم آستانه: {e}")

    def stop(self):
        """توقف Whale Radar"""
        self.running = False
        for exchange, ws in self.ws_connections.items():
            try:
                ws.close()
            except:
                pass
        logger.info("Whale Radar متوقف شد")

    def get_stats(self):
        """آمار فعلی"""
        return {
            "running": self.running,
            "connected": self.connected,
            "binance": self.stats["binance"],
            "bybit": self.stats["bybit"],
            "symbols_count": len(self.symbols),
            "total_alerts": self.total_alerts_sent,
        }

    def format_whale_alert(self, alert):
        """فرمت‌بندی هشدار نهنگ برای تلگرام"""
        alert_type = alert.get("type", "WHALE_ALERT")
        symbol = alert.get("symbol", "")
        base = alert.get("base", symbol)
        direction = alert.get("direction", "buy")
        direction_fa = alert.get("direction_farsi", "")
        time_str = alert.get("time_str", "")
        exchange = alert.get("exchange", "")

        # فرمت قیمت
        current = alert.get("current_price", alert.get("price", 0))
        if current < 1:
            fmt = lambda x: f"{x:.6f}"
        elif current < 100:
            fmt = lambda x: f"{x:.4f}"
        else:
            fmt = lambda x: f"{x:.2f}"

        if alert_type == "SINGLE_WHALE":
            # هشدار تک‌ترید بزرگ
            value = alert.get("value_usdt", 0)
            price = alert.get("price", 0)
            qty = alert.get("qty", 0)

            emoji = "🐋💥" if direction == "buy" else "🐋💥"
            msg = f"""{emoji} نهنگ بزرگ - {direction_fa} {base}

💰 حجم: {value/1e6:.2f}M USDT
💵 قیمت: {fmt(price)}
📊 مقدار: {qty}
🏦 صرافی: {exchange}
⏰ زمان: {time_str}

⚡ هشدار لحظه‌ای - سریع‌تر از کانال‌های تلگرام

⚠️ قبل از ورود، چارت رو بررسی کن"""

        else:
            # هشدار تجمع نهنگ
            count = alert.get("cluster_count", 0)
            total = alert.get("total_value_usdt", 0)
            avg_price = alert.get("avg_price", 0)
            largest = alert.get("largest_trade", 0)
            opposite = alert.get("opposite_count", 0)
            window = alert.get("window_seconds", 60)
            exchanges = alert.get("exchanges", [])

            emoji = "🟢🐋" if direction == "buy" else "🔴🐋"
            exchanges_str = " + ".join(exchanges) if exchanges else exchange

            msg = f"""{emoji} تجمع نهنگ - {direction_fa} {base}

📊 تعداد: {count} ترید در {window} ثانیه
💰 حجم کل: {total/1e6:.2f}M USDT
💵 قیمت فعلی: {fmt(current)}
📈 میانگین قیمت نهنگ: {fmt(avg_price)}
🔝 بزرگترین ترید: {largest/1e6:.2f}M USDT
🏦 صرافی‌ها: {exchanges_str}
🔄 ترید مخالف: {opposite}
⏰ زمان: {time_str}

⚡ هشدار لحظه‌ای - سریع‌تر از کانال‌های تلگرام

⚠️ قبل از ورود، چارت رو بررسی کن"""

        return msg
