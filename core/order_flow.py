# -*- coding: utf-8 -*-
"""
تحلیل Order Flow - جریان سفارشات
تحلیل عدم تعادل خرید/فروش، حجم کندل‌ها، دلتای تریدهای تیکر
"""

import logging
import numpy as np
from config import ORDER_FLOW_LOOKBACK, DELTA_THRESHOLD, LARGE_VOLUME_MULTIPLIER

logger = logging.getLogger(__name__)


class OrderFlowAnalyzer:
    """تحلیل جریان سفارشات و عدم تعادل بازار"""

    def __init__(self):
        self.lookback = ORDER_FLOW_LOOKBACK
        self.delta_threshold = DELTA_THRESHOLD
        self.large_vol_mult = LARGE_VOLUME_MULTIPLIER

    def analyze_candle_flow(self, candles):
        """
        تحلیل جریان سفارشات از روی کندل‌ها
        استفاده از takerBuyVolume که Binance ارائه میده

        برمی‌گردونه:
        {
            "bullish_volume": float,  # حجم خرید
            "bearish_volume": float,  # حجم فروش
            "delta": float,           # تفاوت خرید - فروش
            "delta_ratio": float,     # نسبت خرید/فروش
            "large_candles": list,   # کندل‌های حجم بزرگ
            "trend": str,            # "bullish" / "bearish" / "neutral"
            "score": int,            # 0-100
            "signals": list,         # لیست سیگنال‌های تشخیص داده شده
        }
        """
        if len(candles) < 10:
            return self._empty_result()

        recent = candles[-self.lookback:]
        signals = []

        # محاسبه حجم خرید و فروش
        total_volume = sum(c["volume"] for c in recent)
        total_taker_buy = sum(c.get("takerBuyVolume", 0) for c in recent)

        if total_volume == 0:
            return self._empty_result()

        bullish_volume = total_taker_buy
        bearish_volume = total_volume - total_taker_buy
        delta = bullish_volume - bearish_volume
        delta_ratio = bullish_volume / bearish_volume if bearish_volume > 0 else float("inf")

        # روند حجمی
        if delta_ratio >= self.delta_threshold:
            trend = "bullish"
            signals.append(f"فشار خریدار قوی (نسبت {delta_ratio:.2f}:1)")
        elif delta_ratio <= 1.0 / self.delta_threshold:
            trend = "bearish"
            signals.append(f"فشار فروشنده قوی (نسبت {1/delta_ratio:.2f}:1)")
        else:
            trend = "neutral"
            signals.append(f"تعادل نسبی (نسبت {delta_ratio:.2f}:1)")

        # شناسایی کندل‌های حجم بزرگ (anomaly)
        avg_volume = total_volume / len(recent)
        large_candles = []
        for c in recent:
            if c["volume"] > avg_volume * self.large_vol_mult:
                is_bullish = c["close"] >= c["open"]
                large_candles.append({
                    "time": c["time"],
                    "volume": c["volume"],
                    "bullish": is_bullish,
                    "price": c["close"],
                })
                signals.append(
                    f"کندل حجم بزرگ {'صعودی' if is_bullish else 'نزولی'} در {c['close']:.4f}"
                )

        # تحلیل روند دلتا در 10 کندل اخیر
        recent_10 = recent[-10:]
        deltas = []
        for c in recent_10:
            vol = c["volume"]
            taker_buy = c.get("takerBuyVolume", 0)
            if vol > 0:
                d = (taker_buy - (vol - taker_buy)) / vol
                deltas.append(d)

        delta_trend = "increasing" if len(deltas) >= 4 else "unknown"
        if len(deltas) >= 4:
            half = len(deltas) // 2
            first_half_avg = np.mean(deltas[:half])
            second_half_avg = np.mean(deltas[half:])
            if second_half_avg > first_half_avg:
                delta_trend = "increasing"
                signals.append("دلتای در حال افزایش - روند خرید در حال تقویته")
            else:
                delta_trend = "decreasing"
                signals.append("دلتای در حال کاهش - روند فروش در حال تقویته")

        # محاسبه امتیاز
        score = self._calculate_score(delta_ratio, trend, large_candles, delta_trend)

        return {
            "bullish_volume": bullish_volume,
            "bearish_volume": bearish_volume,
            "delta": delta,
            "delta_ratio": delta_ratio,
            "large_candles": large_candles,
            "trend": trend,
            "delta_trend": delta_trend,
            "score": score,
            "signals": signals,
        }

    def analyze_trade_flow(self, trades):
        """
        تحلیل جریان تریدهای اخیر (tick-level)
        استفاده از isBuyerMaker برای تشخیص خرید/فروش market

        برمی‌گردونه:
        {
            "buy_volume": float,
            "sell_volume": float,
            "delta": float,
            "ratio": float,
            "large_trades": list,
            "trend": str,
        }
        """
        if not trades:
            return self._empty_trade_result()

        buy_volume = 0
        sell_volume = 0
        large_trades = []

        # محاسبه میانگین حجم برای شناسایی تریدهای بزرگ
        all_volumes = [t["price"] * t["qty"] for t in trades]
        avg_trade = np.mean(all_volumes) if all_volumes else 0
        large_threshold = avg_trade * 5  # 5 برابر میانگین

        for t in trades:
            notional = t["price"] * t["qty"]
            # isBuyerMaker=False => خریدار taker => خرید market
            # isBuyerMaker=True => فروشنده taker بود => فروش market
            if t["isBuyerMaker"]:
                sell_volume += notional
                direction = "sell"
            else:
                buy_volume += notional
                direction = "buy"

            if notional > large_threshold:
                large_trades.append({
                    "price": t["price"],
                    "value": notional,
                    "direction": direction,
                })

        total = buy_volume + sell_volume
        delta = buy_volume - sell_volume
        ratio = buy_volume / sell_volume if sell_volume > 0 else float("inf")

        if ratio >= self.delta_threshold:
            trend = "bullish"
        elif ratio <= 1.0 / self.delta_threshold:
            trend = "bearish"
        else:
            trend = "neutral"

        return {
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "delta": delta,
            "ratio": ratio,
            "large_trades": large_trades,
            "trend": trend,
        }

    def _calculate_score(self, delta_ratio, trend, large_candles, delta_trend):
        """محاسبه امتیاز 0-100"""
        score = 50  # پایه

        # امتیاز نسبت دلتا
        if trend == "bullish":
            score += min(20, int((delta_ratio - 1) * 10))
        elif trend == "bearish":
            score -= min(20, int((1 - 1/delta_ratio) * 10)) if delta_ratio > 0 else 20

        # امتیاز کندل‌های حجم بزرگ
        bull_large = sum(1 for c in large_candles if c["bullish"])
        bear_large = sum(1 for c in large_candles if not c["bullish"])
        score += (bull_large - bear_large) * 3

        # امتیاز روند دلتا
        if delta_trend == "increasing":
            score += 10
        elif delta_trend == "decreasing":
            score -= 10

        return max(0, min(100, score))

    def _empty_result(self):
        return {
            "bullish_volume": 0,
            "bearish_volume": 0,
            "delta": 0,
            "delta_ratio": 1.0,
            "large_candles": [],
            "trend": "neutral",
            "delta_trend": "unknown",
            "score": 50,
            "signals": ["داده ناکافی"],
        }

    def _empty_trade_result(self):
        return {
            "buy_volume": 0,
            "sell_volume": 0,
            "delta": 0,
            "ratio": 1.0,
            "large_trades": [],
            "trend": "neutral",
        }
