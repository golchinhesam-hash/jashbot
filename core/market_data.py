# -*- coding: utf-8 -*-
"""
ماژول دریافت داده بازار از Binance API عمومی (data-api.binance.vision)
شامل: قیمت، کندل، حجم، order book

نکته: api.binance.com روی برخی آی‌پی‌ها (مثل Render Oregon) محدود شده (451).
از data-api.binance.vision استفاده می‌کنیم که بدون محدودیت جغرافیایی هست.
"""

import requests
import time
import logging
from config import (
    BINANCE_BASE_URL,
    CANDLE_LIMIT,
    MIN_24H_VOLUME,
    MIN_24H_VOLUME_SHITCOIN,
    SHITCOIN_SYMBOLS,
    KCEX_SYMBOLS,
    USE_KCEX_FILTER,
)

logger = logging.getLogger(__name__)

# API fallback list - اولین یکی که کار کنه استفاده می‌شه
API_BASES = [
    "https://data-api.binance.vision",   # بدون محدودیت جغرافیایی
    "https://api.binance.com",            # اصلی (شاید روی بعضی سرورها کار کنه)
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]


class MarketData:
    """دریافت داده بازار از Binance"""

    def __init__(self):
        self.base_url = BINANCE_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CryptoSignalBot/1.0"
        })
        self._working_base = None  # اولین base که کار می‌کنه

    def _get_base(self):
        """اولین API base که جواب بده رو پیدا کن"""
        if self._working_base:
            return self._working_base

        for base in API_BASES:
            try:
                r = self.session.get(f"{base}/api/v3/ping", timeout=5)
                if r.status_code == 200:
                    self._working_base = base
                    logger.info(f"✅ Binance API فعال: {base}")
                    return base
            except:
                continue

        # fallback به base_url اصلی
        self._working_base = self.base_url
        return self._working_base

    def _request(self, endpoint, params=None):
        """درخواست به Binance API با retry"""
        base = self._get_base()
        url = f"{base}{endpoint}"
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.warning(f"تلاش {attempt+1} ناموفق برای {endpoint}: {e}")
                # اگه 451 یا 403 بود، base رو عوض کن
                if hasattr(resp, 'status_code') and resp.status_code in (451, 403):
                    self._working_base = None
                    base = self._get_base()
                    url = f"{base}{endpoint}"
                if attempt < 2:
                    time.sleep(2)
                else:
                    raise
        return None

    def get_usdt_symbols(self):
        """
        لیست ارزهای USDT - فیلتر شده بر اساس صرافی KCEX
        اگه USE_KCEX_FILTER=True باشه، فقط ارزهایی که تو KCEX هستن برمی‌گردن
        شامل:
        - ارزهای اصلی KCEX با حجم > MIN_24H_VOLUME
        - شت‌کوین‌های KCEX با حجم > MIN_24H_VOLUME_SHITCOIN
        برمی‌گردونه لیست دیکشنری: [{symbol, volume, priceChange, is_shitcoin}, ...]
        """
        try:
            data = self._request("/api/v3/ticker/24hr")
            symbols = []
            shitcoin_set = set(SHITCOIN_SYMBOLS)
            kcex_set = set(KCEX_SYMBOLS) if USE_KCEX_FILTER else None

            for item in data:
                symbol = item.get("symbol", "")
                if not symbol.endswith("USDT"):
                    continue
                # حذف ارزهای leveraged و استیبل‌کوین
                base = symbol.replace("USDT", "")
                skip = ["UP", "DOWN", "BULL", "BEAR"]
                if any(base.endswith(s) for s in skip):
                    continue
                if base in ["USDC", "BUSD", "TUSD", "DAI", "FDUSD"]:
                    continue

                # فیلتر KCEX: اگه روشن باشه، فقط ارزهای KCEX
                if kcex_set is not None and symbol not in kcex_set:
                    continue

                quote_volume = float(item.get("quoteVolume", 0))
                is_shitcoin = symbol in shitcoin_set

                # اگه شت‌کوین لیست ثابت هست، با حداقل حجم شت‌کوین بررسی کن
                if is_shitcoin:
                    if quote_volume < MIN_24H_VOLUME_SHITCOIN:
                        continue
                else:
                    # ارزهای اصلی با حداقل حجم بالا
                    if quote_volume < MIN_24H_VOLUME:
                        # اگه حجمش پایینه ولی بالای حداقل شت‌کوین هست، شاید شت‌کوین باشه
                        if quote_volume >= MIN_24H_VOLUME_SHITCOIN:
                            # بررسی اگه قیمت خیلی پایین باشه یا درصد تغییر بالا، شت‌کوین در نظر بگیر
                            price = float(item.get("lastPrice", 0))
                            price_change = abs(float(item.get("priceChangePercent", 0)))
                            if price > 0 and (price < 0.01 or price_change > 10):
                                is_shitcoin = True
                            else:
                                continue
                        else:
                            continue

                symbols.append({
                    "symbol": symbol,
                    "base": base,
                    "volume": quote_volume,
                    "priceChange": float(item.get("priceChangePercent", 0)),
                    "lastPrice": float(item.get("lastPrice", 0)),
                    "high": float(item.get("highPrice", 0)),
                    "low": float(item.get("lowPrice", 0)),
                    "is_shitcoin": is_shitcoin,
                })

            # مرتب بر اساس حجم نزولی
            symbols.sort(key=lambda x: x["volume"], reverse=True)

            main_count = sum(1 for s in symbols if not s["is_shitcoin"])
            shit_count = sum(1 for s in symbols if s["is_shitcoin"])
            logger.info(f"تعداد {len(symbols)} ارز یافت شد ({main_count} اصلی + {shit_count} شت‌کوین)")

            # لاگ کردن ارزهای KCEX که روی Binance موجود نبودن
            if kcex_set is not None:
                found_symbols = set(s["symbol"] for s in symbols)
                # ارزهای KCEX که volume‌شون کم بوده و فیلتر شدن
                low_volume = set()
                # ارزهای KCEX که اصلاً تو پاسخ Binance نبودن
                missing = kcex_set - found_symbols - low_volume
                # بررسی دقیق: کدوم KCEX نبودن
                all_binance_symbols = set(item.get("symbol", "") for item in data)
                not_on_binance = kcex_set - all_binance_symbols
                if not_on_binance:
                    missing_list = sorted(not_on_binance)
                    logger.warning(f"⚠️ {len(not_on_binance)} ارز KCEX روی Binance موجود نیست: {', '.join(missing_list)}")

            return symbols
        except Exception as e:
            logger.error(f"خطا در دریافت لیست ارزها: {e}")
            return []

    def get_candles(self, symbol, interval="1h", limit=CANDLE_LIMIT):
        """
        دریافت کندل‌های OHLCV
        برمی‌گردونه لیست دیکشنری: [{time, open, high, low, close, volume}, ...]
        """
        try:
            data = self._request("/api/v3/klines", {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            })
            candles = []
            for k in data:
                candles.append({
                    "time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "closeTime": k[6],
                    "quoteVolume": float(k[7]),
                    "trades": int(k[8]),
                    "takerBuyVolume": float(k[9]),
                    "takerBuyQuoteVolume": float(k[10]),
                })
            return candles
        except Exception as e:
            logger.error(f"خطا در دریافت کندل‌های {symbol} {interval}: {e}")
            return []

    def get_order_book(self, symbol, limit=100):
        """
        دریافت order book (bids + asks)
        برمی‌گردونه: {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}
        """
        try:
            data = self._request("/api/v3/depth", {
                "symbol": symbol,
                "limit": limit
            })
            bids = [[float(b[0]), float(b[1])] for b in data.get("bids", [])]
            asks = [[float(a[0]), float(a[1])] for a in data.get("asks", [])]
            return {"bids": bids, "asks": asks}
        except Exception as e:
            logger.error(f"خطا در دریافت order book {symbol}: {e}")
            return {"bids": [], "asks": []}

    def get_recent_trades(self, symbol, limit=500):
        """
        دریافت تریدهای اخیر برای تحلیل جریان سفارشات
        از aggTrades استفاده می‌کنه - قابل اعتمادتر از trades
        """
        try:
            data = self._request("/api/v3/aggTrades", {
                "symbol": symbol,
                "limit": min(limit, 500)
            })
            trades = []
            for t in data:
                trades.append({
                    "id": t.get("a", 0),
                    "price": float(t.get("p", 0)),
                    "qty": float(t.get("q", 0)),
                    "time": t.get("T", 0),
                    "isBuyerMaker": bool(t.get("m", False)),
                    # m=True یعنی فروشنده maker بود => فروش market
                    # m=False یعنی خریدار taker بود => خرید market
                })
            return trades
        except Exception as e:
            logger.error(f"خطا در دریافت تریدهای {symbol}: {e}")
            return []

    def get_multi_timeframe(self, symbol, intervals):
        """
        دریافت داده چند تایم‌فریم
        برمی‌گردونه: {"15m": [...], "1h": [...], "4h": [...]}
        """
        result = {}
        for tf in intervals:
            result[tf] = self.get_candles(symbol, tf)
            time.sleep(0.1)  # محترم کردن rate limit
        return result

    def get_ticker_price(self, symbol):
        """قیمت لحظه‌ای"""
        try:
            data = self._request("/api/v3/ticker/price", {"symbol": symbol})
            return float(data["price"])
        except:
            return None
