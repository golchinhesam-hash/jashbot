# -*- coding: utf-8 -*-
"""
Market Context Analyzer
تحلیل زمینه بازار برای فیلتر کردن سیگنال‌های ضعیف
شامل:
1. BTC Trend Direction (تأثیر BTC روی altcoin)
2. Market Regime Detection (ADX-based: Trending vs Ranging)
3. BTC-Altcoin Correlation
4. Market Structure (BOS/CHoCH)
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class MarketContextAnalyzer:
    """
    تحلیل زمینه کلی بازار
    برای جلوگیری از سیگنال‌هایی که برخلاف جهت اصلی بازار هستن
    """

    def __init__(self):
        # ADX settings
        self.adx_period = 14
        self.adx_threshold_trending = 25
        self.adx_threshold_ranging = 20
        # Correlation settings
        self.corr_lookback = 20
        # Structure settings
        self.structure_lookback = 50

    def calculate_adx(self, candles):
        """
        محاسبه ADX (Average Directional Index)
        برای تشخیص رونددار بودن یا رنج بودن بازار
        
        ADX > 25: روند قوی
        ADX 20-25: روند متوسط
        ADX < 20: رنج
        """
        if len(candles) < self.adx_period * 2 + 1:
            return {"adx": 50, "di_plus": 50, "di_minus": 50, "regime": "unknown"}

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]

        # Calculate +DM and -DM
        plus_dm = []
        minus_dm = []
        tr_list = []

        for i in range(1, len(candles)):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]

            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)

            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)

            # True Range
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            tr_list.append(tr)

        # Smooth with Wilder's method
        def wilder_smooth(values, period):
            smoothed = [np.mean(values[:period])]
            for i in range(period, len(values)):
                smoothed.append(smoothed[-1] - smoothed[-1] / period + values[i])
            return smoothed

        atr = wilder_smooth(tr_list, self.adx_period)
        smoothed_plus_dm = wilder_smooth(plus_dm, self.adx_period)
        smoothed_minus_dm = wilder_smooth(minus_dm, self.adx_period)

        if len(atr) < 2 or atr[-1] == 0:
            return {"adx": 50, "di_plus": 50, "di_minus": 50, "regime": "unknown"}

        # +DI and -DI
        di_plus = 100 * smoothed_plus_dm[-1] / atr[-1] if len(smoothed_plus_dm) > 0 else 0
        di_minus = 100 * smoothed_minus_dm[-1] / atr[-1] if len(smoothed_minus_dm) > 0 else 0

        # DX
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) > 0 else 0

        # ADX (smooth DX)
        dx_values = []
        for i in range(len(smoothed_plus_dm)):
            if i < len(atr) and atr[i] > 0:
                pp = smoothed_plus_dm[i]
                mm = smoothed_minus_dm[i] if i < len(smoothed_minus_dm) else 0
                if pp + mm > 0:
                    dx_values.append(100 * abs(pp - mm) / (pp + mm))

        adx = np.mean(dx_values[-self.adx_period:]) if dx_values else dx

        # Determine regime
        if adx > self.adx_threshold_trending:
            if di_plus > di_minus:
                regime = "strong_trend_up"
            else:
                regime = "strong_trend_down"
        elif adx > self.adx_threshold_ranging:
            if di_plus > di_minus:
                regime = "trend_up"
            else:
                regime = "trend_down"
        else:
            regime = "ranging"

        return {
            "adx": round(adx, 2),
            "di_plus": round(di_plus, 2),
            "di_minus": round(di_minus, 2),
            "regime": regime,
        }

    def analyze_btc_trend(self, btc_candles):
        """
        تحلیل ترند BTC
        Returns: trend direction, strength, recent momentum
        """
        if not btc_candles or len(btc_candles) < 20:
            return {"trend": "unknown", "strength": 0, "momentum": 0, "score": 50}

        closes = [c["close"] for c in btc_candles]
        current = closes[-1]

        # EMA 20
        ema20 = self._calculate_ema(closes, 20)
        # EMA 50
        ema50 = self._calculate_ema(closes, 50)

        if len(ema20) < 2 or len(ema50) < 1:
            return {"trend": "unknown", "strength": 0, "momentum": 0, "score": 50}

        # Trend direction
        if current > ema20[-1] > ema50[-1]:
            trend = "bullish"
            score = 70
        elif current < ema20[-1] < ema50[-1]:
            trend = "bearish"
            score = 30
        elif current > ema20[-1]:
            trend = "weak_bullish"
            score = 55
        elif current < ema20[-1]:
            trend = "weak_bearish"
            score = 45
        else:
            trend = "neutral"
            score = 50

        # Momentum (last 5 candles change %)
        if len(closes) >= 6:
            momentum = (closes[-1] - closes[-6]) / closes[-6] * 100
        else:
            momentum = 0

        # Strength (how far from EMA20)
        dist_from_ema20 = abs(current - ema20[-1]) / current * 100

        return {
            "trend": trend,
            "strength": round(dist_from_ema20, 2),
            "momentum": round(momentum, 2),
            "score": score,
            "ema20": ema20[-1],
            "ema50": ema50[-1],
        }

    def calculate_correlation(self, symbol_candles, btc_candles):
        """
        محاسبه همبستگی بین ارز و BTC
        Returns: correlation coefficient (-1 to 1)
        """
        if not symbol_candles or not btc_candles:
            return {"correlation": 0, "alignment": "unknown"}

        # Get closing prices
        symbol_closes = [c["close"] for c in symbol_candles[-self.corr_lookback:]]
        btc_closes = [c["close"] for c in btc_candles[-self.corr_lookback:]]

        if len(symbol_closes) < 10 or len(btc_closes) < 10:
            return {"correlation": 0, "alignment": "unknown"}

        # Calculate returns
        symbol_returns = []
        btc_returns = []

        for i in range(1, len(symbol_closes)):
            symbol_returns.append((symbol_closes[i] - symbol_closes[i - 1]) / symbol_closes[i - 1])
            btc_returns.append((btc_closes[i] - btc_closes[i - 1]) / btc_closes[i - 1])

        if len(symbol_returns) < 5:
            return {"correlation": 0, "alignment": "unknown"}

        # Pearson correlation
        corr = np.corrcoef(symbol_returns, btc_returns)[0, 1]
        if np.isnan(corr):
            corr = 0

        if corr > 0.7:
            alignment = "strong_positive"
        elif corr > 0.3:
            alignment = "positive"
        elif corr < -0.7:
            alignment = "strong_negative"
        elif corr < -0.3:
            alignment = "negative"
        else:
            alignment = "neutral"

        return {
            "correlation": round(corr, 3),
            "alignment": alignment,
        }

    def detect_market_structure(self, candles):
        """
        تشخیص ساختار بازار (BOS/CHoCH)
        
        Break of Structure (BOS): شکست high/low قبلی در جهت ترند
        Change of Character (CHoCH): اولین شکست خلاف جهت ترند = تغییر احتمالی
        """
        if len(candles) < self.structure_lookback:
            return {"structure": "unknown", "bos": False, "choch": False}

        highs = [c["high"] for c in candles[-self.structure_lookback:]]
        lows = [c["low"] for c in candles[-self.structure_lookback:]]
        closes = [c["close"] for c in candles[-self.structure_lookback:]]

        # Find swing highs and lows (simplified)
        swing_highs = []
        swing_lows = []

        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
                swing_highs.append((i, highs[i]))
            if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
                swing_lows.append((i, lows[i]))

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return {"structure": "unknown", "bos": False, "choch": False}

        # Check for BOS (higher high in uptrend / lower low in downtrend)
        last_two_highs = swing_highs[-2:]
        last_two_lows = swing_lows[-2:]

        bos_bullish = last_two_highs[-1][1] > last_two_highs[0][1]
        bos_bearish = last_two_lows[-1][1] < last_two_lows[0][1]

        # Check for CHoCH (first break against trend)
        # In uptrend: lower low = CHoCH
        # In downtrend: higher high = CHoCH
        recent_trend = "up" if closes[-1] > np.mean(closes[-20:]) else "down"

        choch_bearish = recent_trend == "up" and last_two_lows[-1][1] < last_two_lows[0][1]
        choch_bullish = recent_trend == "down" and last_two_highs[-1][1] > last_two_highs[0][1]

        if bos_bullish:
            structure = "bullish_bos"
        elif bos_bearish:
            structure = "bearish_bos"
        elif choch_bullish:
            structure = "bullish_choch"
        elif choch_bearish:
            structure = "bearish_choch"
        else:
            structure = "consolidating"

        return {
            "structure": structure,
            "bos": bos_bullish or bos_bearish,
            "choch": choch_bullish or choch_bearish,
            "recent_trend": recent_trend,
            "swing_highs": len(swing_highs),
            "swing_lows": len(swing_lows),
        }

    def analyze(self, symbol_candles, btc_candles):
        """
        تحلیل کامل زمینه بازار
        """
        # 1. BTC Trend
        btc_trend = self.analyze_btc_trend(btc_candles)

        # 2. Market Regime for symbol
        regime = self.calculate_adx(symbol_candles)

        # 3. BTC Correlation
        correlation = self.calculate_correlation(symbol_candles, btc_candles)

        # 4. Market Structure
        structure = self.detect_market_structure(symbol_candles)

        # 5. Combined Analysis
        signals = []
        score_adjustment = 0
        direction_filter = None  # None = no filter, or "LONG"/"SHORT"

        # BTC Trend Filter
        btc_direction = btc_trend["trend"]
        if btc_direction in ["bullish", "weak_bullish"]:
            signals.append(f"🟢 BTC ترند صعودی (+{btc_trend['momentum']:.1f}%)")
            score_adjustment += 5
        elif btc_direction in ["bearish", "weak_bearish"]:
            signals.append(f"🔴 BTC ترند نزولی ({btc_trend['momentum']:.1f}%)")
            score_adjustment -= 5
        else:
            signals.append("⚪ BTC خنثی")

        # Strong BTC trend = filter opposite signals
        if btc_direction == "bullish" and btc_trend["strength"] > 2:
            direction_filter = "LONG"
            signals.append("🚨 سیگنال SHORT فیلتر شد (BTC قوی صعودی)")
        elif btc_direction == "bearish" and btc_trend["strength"] > 2:
            direction_filter = "SHORT"
            signals.append("🚨 سیگنال LONG فیلتر شد (BTC قوی نزولی)")

        # Correlation Filter
        corr = correlation["correlation"]
        if corr > 0.7:
            signals.append(f"🔗 همبستگی قوی با BTC ({corr:.2f}) - جهت باید هماهنگ باشه")
            # If strong correlation, enforce BTC direction
            if btc_direction == "bullish":
                direction_filter = "LONG"
            elif btc_direction == "bearish":
                direction_filter = "SHORT"
        elif corr > 0.3:
            signals.append(f"🔗 همبستگی متوسط با BTC ({corr:.2f})")
        elif corr < -0.3:
            signals.append(f"🔀 واگرایی با BTC ({corr:.2f}) - altcoin مستقله")
            score_adjustment += 3

        # Market Regime Filter
        reg = regime["regime"]
        if reg in ["strong_trend_up", "strong_trend_down"]:
            signals.append(f"📈 بازار روند قوی (ADX: {regime['adx']})")
            score_adjustment += 5
        elif reg == "ranging":
            signals.append(f"↔️ بازار رنج (ADX: {regime['adx']}) - فقط ستاپ‌های سوپر قوی")
            score_adjustment -= 10  # Penalty for ranging market

        # Structure Filter
        struct = structure["structure"]
        if "bullish_bos" in struct:
            signals.append("🚀 Break of Structure صعودی")
            score_adjustment += 5
        elif "bearish_bos" in struct:
            signals.append("🔻 Break of Structure نزولی")
            score_adjustment -= 5
        elif "choch" in struct:
            signals.append(f"⚠️ Change of Character ({struct}) - احتمال برگشت")
            score_adjustment -= 3

        return {
            "btc_trend": btc_trend,
            "regime": regime,
            "correlation": correlation,
            "structure": structure,
            "signals": signals,
            "score_adjustment": score_adjustment,
            "direction_filter": direction_filter,
            "context_score": 50 + score_adjustment,
        }

    def _calculate_ema(self, values, period):
        """محاسبه EMA"""
        if len(values) < period:
            return []
        multiplier = 2 / (period + 1)
        ema = [np.mean(values[:period])]
        for i in range(period, len(values)):
            ema.append(values[i] * multiplier + ema[-1] * (1 - multiplier))
        return ema
