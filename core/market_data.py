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
        """درخواست به Binance API با retry و fallback"""
        for attempt in range(3):
            base = self._get_base()
            url = f"{base}{endpoint}"
            resp = None
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (451, 403):
                    logger.warning(f"Geo-restricted ({resp.status_code}) از {base}، تلاش با base بعدی...")
                    self._working_base = None
                    # بلافاصله base بعدی رو امتحان کن
                    for alt_base in API_BASES:
                        if alt_base == base:
                            continue
                        try:
                            resp2 = self.session.get(f"{alt_base}{endpoint}", params=params, timeout=15)
                            if resp2.status_code == 200:
                                self._working_base = alt_base
                                logger.info(f"✅ Base جایگزین پیدا شد: {alt_base}")
                                return resp2.json()
                        except:
                            continue
                    if attempt < 2:
                        time.sleep(2)
                        continue
                else:
                    logger.warning(f"تلاش {attempt+1} ناموفق برای {endpoint}: HTTP {resp.status_code}")
                    if attempt < 2:
                        time.sleep(2)
                        continue
            except Exception as e:
                logger.warning(f"تلاش {attempt+1} ناموفق برای {endpoint}: {e}")
                # خطای شبکه - base رو reset کن
                self._working_base = None
                if attempt < 2:
                    time.sleep(2)
                    continue
        
        # آخرین تلاش: Bybit API به عنوان fallback (بدون محدودیت جغرافیایی)
        return self._request_bybit_fallback(endpoint, params)

    def _request_bybit_fallback(self, endpoint, params=None):
        """Fallback به Bybit API وقتی Binance کار نمی‌کنه"""
        # فقط برای endpoint‌هایی که Bybit پشتیبانی می‌کنه
        try:
            if "/api/v3/ticker/24hr" in endpoint:
                # Bybit ticker endpoint
                resp = self.session.get(
                    "https://api.bybit.com/v5/market/tickers",
                    params={"category": "spot"},
                    timeout=15
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("retCode") == 0:
                        # تبدیل فرمت Bybit به Binance
                        tickers = data.get("result", {}).get("list", [])
                        binance_format = []
                        for t in tickers:
                            if not t.get("symbol", "").endswith("USDT"):
                                continue
                            binance_format.append({
                                "symbol": t.get("symbol", ""),
                                "lastPrice": t.get("lastPrice", "0"),
                                "priceChangePercent": t.get("price24hPcnt", "0") if "price24hPcnt" in t else "0",
                                "quoteVolume": t.get("turnover24h", "0"),
                                "highPrice": t.get("highPrice24h", "0"),
                                "lowPrice": t.get("lowPrice24h", "0"),
                                "volume": t.get("volume24h", "0"),
                            })
                        logger.info(f"✅ Bybit fallback: {len(binance_format)} ticker دریافت شد")
                        return binance_format
        except Exception as e:
            logger.error(f"Bybit fallback هم کار نکرد: {e}")
        
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
                if base in ["USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USD1", "USDS", "PAXG", "XAU", "EUR", "GBP", "TRY", "BRL", "AEUR", "EURI"]:
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
        دریافت کندل‌های OHLCV از Binance (با fallback به Bybit)
        برمی‌گردونه لیست دیکشنری: [{time, open, high, low, close, volume}, ...]
        """
        # مپ کردن interval های Binance به Bybit
        bybit_interval_map = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
        
        try:
            data = self._request("/api/v3/klines", {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            })
            if data:
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
            logger.error(f"خطا در دریافت کندل‌های {symbol} {interval} از Binance: {e}")

        # Fallback: Bybit klines
        return self._get_bybit_klines(symbol, interval, limit)

    def _get_bybit_klines(self, symbol, interval="1h", limit=200):
        """دریافت کندل‌ها از Bybit وقتی Binance کار نمی‌کنه"""
        bybit_interval_map = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
        bybit_interval = bybit_interval_map.get(interval, "60")
        
        try:
            # Bybit spot klines
            resp = self.session.get(
                "https://api.bybit.com/v5/market/kline",
                params={
                    "category": "spot",
                    "symbol": symbol,
                    "interval": bybit_interval,
                    "limit": limit
                },
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("retCode") == 0:
                    raw_list = data.get("result", {}).get("list", [])
                    # Bybit برعکس برمی‌گردونه (قدیمی‌ترین آخر)
                    raw_list.reverse()
                    candles = []
                    for k in raw_list:
                        candles.append({
                            "time": int(k[0]),
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "closeTime": int(k[0]) + 3600000,
                            "quoteVolume": float(k[5]) * float(k[4]),  # تقریبی
                            "trades": 0,
                            "takerBuyVolume": float(k[5]) * 0.5,  # تقریبی
                            "takerBuyQuoteVolume": float(k[5]) * float(k[4]) * 0.5,
                        })
                    return candles
        except Exception as e:
            logger.error(f"Bybit klines fallback هم کار نکرد برای {symbol}: {e}")
        
        return []

    def get_order_book(self, symbol, limit=100):
        """
        دریافت order book (bids + asks) با fallback به Bybit
        برمی‌گردونه: {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}
        """
        try:
            data = self._request("/api/v3/depth", {
                "symbol": symbol,
                "limit": limit
            })
            if data:
                bids = [[float(b[0]), float(b[1])] for b in data.get("bids", [])]
                asks = [[float(a[0]), float(a[1])] for a in data.get("asks", [])]
                return {"bids": bids, "asks": asks}
        except Exception as e:
            logger.error(f"خطا در دریافت order book {symbol} از Binance: {e}")

        # Fallback: Bybit
        try:
            resp = self.session.get(
                "https://api.bybit.com/v5/market/orderbook",
                params={"category": "spot", "symbol": symbol, "limit": limit},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("retCode") == 0:
                    bids = [[float(b[0]), float(b[1])] for b in data.get("result", {}).get("bids", [])]
                    asks = [[float(a[0]), float(a[1])] for a in data.get("result", {}).get("asks", [])]
                    return {"bids": bids, "asks": asks}
        except Exception as e:
            logger.error(f"Bybit order book fallback هم کار نکرد {symbol}: {e}")
        
        return {"bids": [], "asks": []}

    def get_recent_trades(self, symbol, limit=500):
        """
        دریافت تریدهای اخیر برای تحلیل جریان سفارشات
        با fallback به Bybit
        """
        try:
            data = self._request("/api/v3/aggTrades", {
                "symbol": symbol,
                "limit": min(limit, 500)
            })
            if data:
                trades = []
                for t in data:
                    trades.append({
                        "id": t.get("a", 0),
                        "price": float(t.get("p", 0)),
                        "qty": float(t.get("q", 0)),
                        "time": t.get("T", 0),
                        "isBuyerMaker": bool(t.get("m", False)),
                    })
                return trades
        except Exception as e:
            logger.error(f"خطا در دریافت تریدهای {symbol} از Binance: {e}")

        # Fallback: Bybit public trades
        try:
            resp = self.session.get(
                "https://api.bybit.com/v5/market/recent-trade",
                params={"category": "spot", "symbol": symbol, "limit": min(limit, 60)},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("retCode") == 0:
                    trades = []
                    for t in data.get("result", {}).get("list", []):
                        trades.append({
                            "id": hash(t.get("execId", "")),
                            "price": float(t.get("price", 0)),
                            "qty": float(t.get("size", 0)),
                            "time": int(t.get("time", 0)),
                            # Bybit: side="Buy" = buyer taker, side="Sell" = seller taker
                            "isBuyerMaker": t.get("side", "") == "Sell",
                        })
                    return trades
        except Exception as e:
            logger.error(f"Bybit trades fallback هم کار نکرد {symbol}: {e}")

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
