# -*- coding: utf-8 -*-
"""
ماژول دریافت داده بازار - چند صرافی (KuCoin + Binance + Bybit)
اولویت: KuCoin (بدون محدودیت جغرافیایی و Cloudflare) → Binance → Bybit
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

# KuCoin API base (بدون محدودیت جغرافیایی، بدون Cloudflare)
KUCOIN_BASE = "https://api.kucoin.com"

# Binance API fallback list
API_BASES = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

# مپ کردن interval‌ها
KUCOIN_INTERVAL_MAP = {"15m": "15min", "1h": "1hour", "4h": "4hour", "1d": "1day"}


class MarketData:
    """دریافت داده بازار از KuCoin (اصلی) + Binance/Bybit (fallback)"""

    def __init__(self):
        self.base_url = BINANCE_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CryptoSignalBot/1.0",
            "Accept": "application/json",
        })
        self._working_base = None
        self._data_source = None  # "kucoin" | "binance" | "bybit"

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

        self._working_base = self.base_url
        return self._working_base

    def _kucoin_get(self, endpoint, params=None):
        """درخواست به KuCoin API"""
        url = f"{KUCOIN_BASE}{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "200000":
                    return data.get("data", [])
            return None
        except Exception as e:
            logger.debug(f"KuCoin خطا {endpoint}: {e}")
            return None

    def get_usdt_symbols(self):
        """
        لیست ارزهای USDT از KuCoin (با fallback به Binance)
        برمی‌گردونه لیست دیکشنری: [{symbol, volume, priceChange, is_shitcoin}, ...]
        """
        # === تلاش 1: KuCoin allTickers ===
        try:
            data = self._kucoin_get("/api/v1/market/allTickers")
            if data:
                symbols = []
                shitcoin_set = set(SHITCOIN_SYMBOLS)
                kcex_set = set(KCEX_SYMBOLS) if USE_KCEX_FILTER else None
                stable_set = {"USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USD1", "USDS", "PAXG", "XAU", "EUR", "GBP", "TRY", "BRL", "AEUR", "EURI"}

                tickers = data.get("ticker", []) if isinstance(data, dict) else data
                for item in tickers:
                    symbol_kc = item.get("symbol", "")  # مثل BTC-USDT
                    if not symbol_kc.endswith("-USDT"):
                        continue
                    base = symbol_kc.replace("-USDT", "")
                    symbol = base + "USDT"  # تبدیل به فرمت Binance

                    # فیلتر استیبل‌کوین و leveraged
                    skip = ["UP", "DOWN", "BULL", "BEAR"]
                    if any(base.endswith(s) for s in skip):
                        continue
                    if base in stable_set:
                        continue

                    if kcex_set is not None and symbol not in kcex_set:
                        continue

                    quote_volume = float(item.get("volValue", 0))
                    if quote_volume == 0:
                        continue
                    is_shitcoin = symbol in shitcoin_set

                    if is_shitcoin:
                        if quote_volume < MIN_24H_VOLUME_SHITCOIN:
                            continue
                    else:
                        if quote_volume < MIN_24H_VOLUME:
                            if quote_volume >= MIN_24H_VOLUME_SHITCOIN:
                                price = float(item.get("last", 0))
                                change_rate = abs(float(item.get("changeRate", 0)) * 100)
                                if price > 0 and (price < 0.01 or change_rate > 10):
                                    is_shitcoin = True
                                else:
                                    continue
                            else:
                                continue

                    symbols.append({
                        "symbol": symbol,
                        "base": base,
                        "volume": quote_volume,
                        "priceChange": float(item.get("changeRate", 0)) * 100,
                        "lastPrice": float(item.get("last", 0)),
                        "high": float(item.get("high", 0)),
                        "low": float(item.get("low", 0)),
                        "is_shitcoin": is_shitcoin,
                    })

                symbols.sort(key=lambda x: x["volume"], reverse=True)

                main_count = sum(1 for s in symbols if not s["is_shitcoin"])
                shit_count = sum(1 for s in symbols if s["is_shitcoin"])
                logger.info(f"✅ KuCoin: {len(symbols)} ارز یافت شد ({main_count} اصلی + {shit_count} شت‌کوین)")
                self._data_source = "kucoin"
                return symbols
        except Exception as e:
            logger.error(f"خطا در دریافت لیست ارزها از KuCoin: {e}")

        # === تلاش 2: Binance ===
        try:
            data = self._request("/api/v3/ticker/24hr")
            if data:
                symbols = []
                shitcoin_set = set(SHITCOIN_SYMBOLS)
                kcex_set = set(KCEX_SYMBOLS) if USE_KCEX_FILTER else None
                stable_set = {"USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USD1", "USDS", "PAXG", "XAU", "EUR", "GBP", "TRY", "BRL", "AEUR", "EURI"}

                for item in data:
                    symbol = item.get("symbol", "")
                    if not symbol.endswith("USDT"):
                        continue
                    base = symbol.replace("USDT", "")
                    skip = ["UP", "DOWN", "BULL", "BEAR"]
                    if any(base.endswith(s) for s in skip):
                        continue
                    if base in stable_set:
                        continue
                    if kcex_set is not None and symbol not in kcex_set:
                        continue

                    quote_volume = float(item.get("quoteVolume", 0))
                    is_shitcoin = symbol in shitcoin_set

                    if is_shitcoin:
                        if quote_volume < MIN_24H_VOLUME_SHITCOIN:
                            continue
                    else:
                        if quote_volume < MIN_24H_VOLUME:
                            if quote_volume >= MIN_24H_VOLUME_SHITCOIN:
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

                symbols.sort(key=lambda x: x["volume"], reverse=True)
                logger.info(f"✅ Binance: {len(symbols)} ارز یافت شد")
                self._data_source = "binance"
                return symbols
        except Exception as e:
            logger.error(f"خطا در دریافت از Binance: {e}")

        return []

    def get_candles(self, symbol, interval="1h", limit=CANDLE_LIMIT):
        """
        دریافت کندل‌های OHLCV
        اولویت: KuCoin → Binance → Bybit
        """
        # === تلاش 1: KuCoin ===
        kc_interval = KUCOIN_INTERVAL_MAP.get(interval, "1hour")
        # تبدیل BTCUSDT → BTC-USDT
        kc_symbol = symbol.replace("USDT", "-USDT")
        try:
            data = self._kucoin_get("/api/v1/market/candles", {
                "symbol": kc_symbol,
                "type": kc_interval,
                "limit": str(limit)
            })
            if data:
                candles = []
                # KuCoin برعکس برمی‌گردونه
                for k in reversed(data):
                    o = float(k[1])
                    c = float(k[2])
                    h = float(k[3])
                    l = float(k[4])
                    v = float(k[5])
                    qv = float(k[6]) if len(k) > 6 else v * c

                    # تخمین takerBuyVolume از روی بدنه کندل
                    # کندل صعودی (close>open): بیشتر خریداران taker بودن
                    # کندل نزولی (close<open): بیشتر فروشندگان taker بودن
                    if v > 0:
                        if c >= o:
                            # صعودی: 60-80% حجم تابع خرید
                            body_pct = (c - o) / (h - l) if (h - l) > 0 else 0.5
                            taker_buy_ratio = 0.55 + body_pct * 0.25  # 0.55 to 0.80
                        else:
                            # نزولی: 20-40% حجم تابع خرید
                            body_pct = (o - c) / (h - l) if (h - l) > 0 else 0.5
                            taker_buy_ratio = 0.45 - body_pct * 0.25  # 0.45 to 0.20
                        taker_buy_vol = v * taker_buy_ratio
                    else:
                        taker_buy_vol = v * 0.5

                    candles.append({
                        "time": int(k[0]) * 1000,
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": v,
                        "closeTime": int(k[0]) * 1000 + 3600000,
                        "quoteVolume": qv,
                        "trades": 0,
                        "takerBuyVolume": taker_buy_vol,
                        "takerBuyQuoteVolume": taker_buy_vol * c,
                    })
                if candles:
                    self._data_source = "kucoin"
                    return candles
        except Exception as e:
            logger.debug(f"KuCoin klines خطا {symbol}: {e}")

        # === تلاش 2: Binance ===
        try:
            base = self._get_base()
            url = f"{base}/api/v3/klines"
            resp = self.session.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
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
                if candles:
                    self._data_source = "binance"
                    return candles
        except Exception as e:
            logger.debug(f"Binance klines خطا {symbol}: {e}")

        # === تلاش 3: Bybit ===
        return self._get_bybit_klines(symbol, interval, limit)

    def _get_bybit_klines(self, symbol, interval="1h", limit=200):
        """دریافت کندل‌ها از Bybit"""
        bybit_interval_map = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
        bybit_interval = bybit_interval_map.get(interval, "60")

        try:
            resp = self.session.get(
                "https://api.bybit.com/v5/market/kline",
                params={"category": "spot", "symbol": symbol, "interval": bybit_interval, "limit": limit},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("retCode") == 0:
                    raw_list = data.get("result", {}).get("list", [])
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
                            "quoteVolume": float(k[5]) * float(k[4]),
                            "trades": 0,
                            "takerBuyVolume": float(k[5]) * 0.5,
                            "takerBuyQuoteVolume": float(k[5]) * float(k[4]) * 0.5,
                        })
                    if candles:
                        self._data_source = "bybit"
                    return candles
        except Exception as e:
            logger.error(f"Bybit klines خطا {symbol}: {e}")

        return []

    def get_order_book(self, symbol, limit=100):
        """دریافت order book - KuCoin → Binance → Bybit"""
        kc_symbol = symbol.replace("USDT", "-USDT")

        # === KuCoin ===
        try:
            data = self._kucoin_get(f"/api/v1/market/orderbook/level2_20", {"symbol": kc_symbol})
            if data:
                bids = [[float(b[0]), float(b[1])] for b in data.get("bids", [])]
                asks = [[float(a[0]), float(a[1])] for a in data.get("asks", [])]
                return {"bids": bids, "asks": asks}
        except Exception as e:
            logger.debug(f"KuCoin orderbook خطا {symbol}: {e}")

        # === Binance ===
        try:
            base = self._get_base()
            url = f"{base}/api/v3/depth"
            resp = self.session.get(url, params={"symbol": symbol, "limit": limit}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                bids = [[float(b[0]), float(b[1])] for b in data.get("bids", [])]
                asks = [[float(a[0]), float(a[1])] for a in data.get("asks", [])]
                return {"bids": bids, "asks": asks}
        except Exception as e:
            logger.debug(f"Binance orderbook خطا {symbol}: {e}")

        # === Bybit ===
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
            logger.debug(f"Bybit orderbook خطا {symbol}: {e}")

        return {"bids": [], "asks": []}

    def get_recent_trades(self, symbol, limit=500):
        """دریافت تریدهای اخیر - KuCoin → Binance → Bybit"""
        kc_symbol = symbol.replace("USDT", "-USDT")

        # === KuCoin ===
        try:
            data = self._kucoin_get("/api/v1/market/histories", {
                "symbol": kc_symbol,
                "limit": str(min(limit, 100))
            })
            if data:
                trades = []
                for t in data:
                    trades.append({
                        "id": hash(t.get("sequence", "")),
                        "price": float(t.get("price", 0)),
                        "qty": float(t.get("size", 0)),
                        "time": int(t.get("time", 0)),
                        # KuCoin: side="buy" = خریدار taker، side="sell" = فروشنده taker
                        "isBuyerMaker": t.get("side", "") == "sell",
                    })
                if trades:
                    return trades
        except Exception as e:
            logger.debug(f"KuCoin trades خطا {symbol}: {e}")

        # === Binance ===
        try:
            base = self._get_base()
            url = f"{base}/api/v3/aggTrades"
            resp = self.session.get(url, params={"symbol": symbol, "limit": min(limit, 500)}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                trades = []
                for t in data:
                    trades.append({
                        "id": t.get("a", 0),
                        "price": float(t.get("p", 0)),
                        "qty": float(t.get("q", 0)),
                        "time": t.get("T", 0),
                        "isBuyerMaker": bool(t.get("m", False)),
                    })
                if trades:
                    return trades
        except Exception as e:
            logger.debug(f"Binance trades خطا {symbol}: {e}")

        # === Bybit ===
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
                            "isBuyerMaker": t.get("side", "") == "Sell",
                        })
                    return trades
        except Exception as e:
            logger.debug(f"Bybit trades خطا {symbol}: {e}")

        return []

    def _request(self, endpoint, params=None):
        """درخواست مستقیم به Binance (fallback)"""
        base = self._get_base()
        url = f"{base}{endpoint}"
        resp = None
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Binance _request خطا {endpoint}: {e}")
        return None

    def get_multi_timeframe(self, symbol, intervals):
        """دریافت داده چند تایم‌فریم"""
        result = {}
        for tf in intervals:
            result[tf] = self.get_candles(symbol, tf)
            time.sleep(0.1)
        return result

    def get_ticker_price(self, symbol):
        """قیمت لحظه‌ای"""
        kc_symbol = symbol.replace("USDT", "-USDT")
        try:
            data = self._kucoin_get("/api/v1/market/orderbook/level1", {"symbol": kc_symbol})
            if data:
                return float(data.get("price", 0))
        except:
            pass
        try:
            data = self._request("/api/v3/ticker/price", {"symbol": symbol})
            if data:
                return float(data["price"])
        except:
            pass
        return None
