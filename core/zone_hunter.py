# -*- coding: utf-8 -*-
"""
ZoneHunter Indicator - استخراج شده از Pine Script
شامل:
1. Triple SuperTrend (3x supertrend با تنظیمات مختلف)
2. Trend Table Dashboard (TTD) - ترند در چند تایم‌فریم
3. VWAP Divergence Detection
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class ZoneHunter:
    """ZoneHunter Indicator - Triple SuperTrend + Multi-Timeframe Trend"""

    def __init__(self):
        # Triple SuperTrend Settings
        self.st_settings = [
            {"period": 7, "multiplier": 2.0, "name": "ST1"},
            {"period": 10, "multiplier": 3.0, "name": "ST2"},
            {"period": 14, "multiplier": 4.0, "name": "ST3"},
        ]
        # TTD EMA lengths
        self.ttd_ema_length = 50

    def calculate_atr(self, candles, period):
        """محاسبه ATR"""
        if len(candles) < period + 1:
            return []

        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)

        # SMA of TR
        atr = []
        for i in range(period - 1, len(tr_values)):
            atr.append(np.mean(tr_values[i - period + 1 : i + 1]))
        return atr

    def calculate_supertrend(self, candles, period, multiplier):
        """
        محاسبه SuperTrend
        Returns: (trend_list, upper_band, lower_band)
        trend: 1 = bullish, -1 = bearish
        """
        if len(candles) < period + 2:
            return None, None, None

        atr = self.calculate_atr(candles, period)
        if not atr:
            return None, None, None

        # Align ATR with candles (ATR starts from index 1)
        src = [c["close"] for c in candles[1:]]

        upper_band = []
        lower_band = []
        trend = []

        for i in range(len(atr)):
            if i >= len(src):
                break

            up = src[i] - multiplier * atr[i]
            dn = src[i] + multiplier * atr[i]

            if i == 0:
                upper_band.append(up)
                lower_band.append(dn)
                trend.append(1)  # default bullish
            else:
                # Upper band
                if src[i - 1] > upper_band[-1]:
                    upper_band.append(max(up, upper_band[-1]))
                else:
                    upper_band.append(up)

                # Lower band
                if src[i - 1] < lower_band[-1]:
                    lower_band.append(min(dn, lower_band[-1]))
                else:
                    lower_band.append(dn)

                # Trend
                if trend[-1] == -1 and src[i] > lower_band[-2]:
                    trend.append(1)
                elif trend[-1] == 1 and src[i] < upper_band[-2]:
                    trend.append(-1)
                else:
                    trend.append(trend[-1])

        return trend, upper_band, lower_band

    def analyze_triple_supertrend(self, candles):
        """
        تحلیل Triple SuperTrend
        وقتی هر 3 تا همزمان سیگنال بدن = سیگنال قوی
        """
        if len(candles) < 20:
            return {"alignment": "none", "score": 50, "signals": []}

        results = []
        all_trends = []

        for setting in self.st_settings:
            trend, up, dn = self.calculate_supertrend(
                candles, setting["period"], setting["multiplier"]
            )
            if trend:
                results.append(
                    {
                        "name": setting["name"],
                        "trend": trend[-1] if trend else 0,
                        "period": setting["period"],
                        "multiplier": setting["multiplier"],
                    }
                )
                all_trends.append(trend[-1] if trend else 0)

        if not results or len(results) < 3:
            return {"alignment": "none", "score": 50, "signals": []}

        signals = []
        bullish_count = sum(1 for t in all_trends if t == 1)
        bearish_count = sum(1 for t in all_trends if t == -1)

        # Check alignment
        if bullish_count == 3:
            alignment = "strong_bullish"
            score = 85
            signals.append("🟢 Triple SuperTrend: همه 3 تا صعودی!")
        elif bearish_count == 3:
            alignment = "strong_bearish"
            score = 85
            signals.append("🔴 Triple SuperTrend: همه 3 تا نزولی!")
        elif bullish_count >= 2:
            alignment = "bullish"
            score = 65
            signals.append(f"🟢 {bullish_count}/3 SuperTrend صعودی")
        elif bearish_count >= 2:
            alignment = "bearish"
            score = 65
            signals.append(f"🔴 {bearish_count}/3 SuperTrend نزولی")
        else:
            alignment = "mixed"
            score = 50
            signals.append("⚪ SuperTrend‌ها مخلوط هستن")

        # Detect crossovers (change in trend)
        for r in results:
            # We'd need historical trends to detect crossovers
            pass

        return {
            "alignment": alignment,
            "score": score,
            "signals": signals,
            "details": results,
            "direction": "LONG" if bullish_count >= 2 else "SHORT" if bearish_count >= 2 else "NEUTRAL",
        }

    def analyze_ttd(self, candles_dict):
        """
        Trend Table Dashboard (TTD)
        چک کردن ترند توی چند تایم‌فریم با EMA

        candles_dict: { '1h': candles_1h, '4h': candles_4h, '1d': candles_1d, ... }
        """
        if not candles_dict:
            return {"alignment": "none", "score": 50, "signals": []}

        timeframe_trends = {}

        for tf, candles in candles_dict.items():
            if not candles or len(candles) < self.ttd_ema_length + 5:
                continue

            # Calculate EMA
            closes = [c["close"] for c in candles]
            ema = self._calculate_ema(closes, self.ttd_ema_length)

            if len(ema) < 3:
                continue

            current_ema = ema[-1]
            prev_ema = ema[-2]
            prev_prev_ema = ema[-3]

            # Determine trend
            if current_ema > prev_ema and prev_ema > prev_prev_ema:
                trend = "bullish"
            elif current_ema < prev_ema and prev_ema < prev_prev_ema:
                trend = "bearish"
            else:
                trend = "neutral"

            timeframe_trends[tf] = trend

        # Count alignments
        bullish_tfs = [tf for tf, t in timeframe_trends.items() if t == "bullish"]
        bearish_tfs = [tf for tf, t in timeframe_trends.items() if t == "bearish"]

        signals = []
        total = len(timeframe_trends)

        if total == 0:
            return {"alignment": "none", "score": 50, "signals": []}

        bull_pct = len(bullish_tfs) / total
        bear_pct = len(bearish_tfs) / total

        if bull_pct >= 0.7:
            alignment = "strong_bullish"
            score = 80
            signals.append(f"🟢 TTD: {len(bullish_tfs)}/{total} تایم‌فریم صعودی")
        elif bear_pct >= 0.7:
            alignment = "strong_bearish"
            score = 80
            signals.append(f"🔴 TTD: {len(bearish_tfs)}/{total} تایم‌فریم نزولی")
        elif bull_pct >= 0.5:
            alignment = "bullish"
            score = 60
            signals.append(f"🟢 TTD: {len(bullish_tfs)}/{total} صعودی")
        elif bear_pct >= 0.5:
            alignment = "bearish"
            score = 60
            signals.append(f"🔴 TTD: {len(bearish_tfs)}/{total} نزولی")
        else:
            alignment = "mixed"
            score = 50
            signals.append(f"⚪ TTD: ترندها مخلوط")

        # Specific timeframe alignment alerts
        important_tfs = ["1h", "4h", "1d"]
        aligned = [tf for tf in important_tfs if tf in timeframe_trends]
        if len(aligned) >= 2:
            trends_aligned = [timeframe_trends[tf] for tf in aligned]
            if all(t == "bullish" for t in trends_aligned):
                signals.append("🚀 1H + 4H + 1D همگی صعودی!")
                score += 10
            elif all(t == "bearish" for t in trends_aligned):
                signals.append("🔻 1H + 4H + 1D همگی نزولی!")
                score += 10

        return {
            "alignment": alignment,
            "score": min(score, 100),
            "signals": signals,
            "timeframe_trends": timeframe_trends,
            "direction": "LONG" if bull_pct >= 0.5 else "SHORT" if bear_pct >= 0.5 else "NEUTRAL",
        }

    def detect_vwap_divergence(self, candles):
        """
        تشخیص VWAP Divergence
        Bullish: قیمت بالاتر ولی VWAP پایین‌تر (قیمت داره از VWAP فاصله می‌گیره صعودی)
        Bearish: قیمت پایین‌تر ولی VWAP بالاتر
        """
        if len(candles) < 20:
            return {"divergence": False, "type": "none", "score": 50}

        # Calculate VWAP (daily session)
        vwap_values = []
        typical_prices = []
        cumulative_tp_vol = 0
        cumulative_vol = 0

        # Reset each day (simplified - in real implementation would detect session changes)
        for c in candles:
            tp = (c["high"] + c["low"] + c["close"]) / 3
            vol = c["volume"]

            typical_prices.append(tp)
            cumulative_tp_vol += tp * vol
            cumulative_vol += vol

            if cumulative_vol > 0:
                vwap_values.append(cumulative_tp_vol / cumulative_vol)
            else:
                vwap_values.append(tp)

        if len(vwap_values) < 10:
            return {"divergence": False, "type": "none", "score": 50}

        # Check recent divergence
        recent_len = min(7, len(vwap_values) - 1)
        recent_vwap = vwap_values[-recent_len:]
        recent_close = [c["close"] for c in candles[-recent_len:]]

        vwap_change = (recent_vwap[-1] - recent_vwap[0]) / recent_vwap[0] * 100
        price_change = (recent_close[-1] - recent_close[0]) / recent_close[0] * 100

        signals = []
        divergence_type = "none"
        score = 50

        # Bullish divergence: price up, VWAP down (or lagging)
        if price_change > 1.5 and vwap_change < price_change * 0.5:
            divergence_type = "bullish_vwap"
            score = 70
            signals.append(f"🟢 VWAP Divergence: قیمت +{price_change:.1f}% ولی VWAP +{vwap_change:.1f}%")

        # Bearish divergence: price down, VWAP up
        elif price_change < -1.5 and vwap_change > price_change * 0.5:
            divergence_type = "bearish_vwap"
            score = 70
            signals.append(f"🔴 VWAP Divergence: قیمت {price_change:.1f}% ولی VWAP {vwap_change:.1f}%")

        # Check if price crossed VWAP
        prev_close = candles[-2]["close"]
        curr_close = candles[-1]["close"]
        curr_vwap = vwap_values[-1]

        if prev_close < curr_vwap and curr_close > curr_vwap:
            signals.append("🟢 قیمت از بالای VWAP رد شد!")
            score += 10
        elif prev_close > curr_vwap and curr_close < curr_vwap:
            signals.append("🔴 قیمت از زیر VWAP رد شد!")
            score += 10

        return {
            "divergence": divergence_type != "none",
            "type": divergence_type,
            "score": min(score, 100),
            "signals": signals,
            "vwap": curr_vwap if vwap_values else None,
            "direction": "LONG" if "bullish" in divergence_type else "SHORT" if "bearish" in divergence_type else "NEUTRAL",
        }

    def _calculate_ema(self, values, period):
        """محاسبه EMA"""
        if len(values) < period:
            return []

        multiplier = 2 / (period + 1)
        ema = [np.mean(values[:period])]  # SMA as first value

        for i in range(period, len(values)):
            ema.append(values[i] * multiplier + ema[-1] * (1 - multiplier))

        return ema

    def analyze(self, candles, candles_4h=None, candles_1d=None):
        """
        تحلیل کامل ZoneHunter
        """
        # Triple SuperTrend
        triple_st = self.analyze_triple_supertrend(candles)

        # TTD
        candles_dict = {"1h": candles}
        if candles_4h:
            candles_dict["4h"] = candles_4h
        if candles_1d:
            candles_dict["1d"] = candles_1d

        ttd = self.analyze_ttd(candles_dict)

        # VWAP Divergence
        vwap_div = self.detect_vwap_divergence(candles)

        # Combine
        direction_votes = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
        reasons = []
        total_score = 50

        # Triple ST votes
        if triple_st["direction"] == "LONG":
            direction_votes["LONG"] += triple_st["score"] / 100
            reasons.extend(triple_st["signals"])
        elif triple_st["direction"] == "SHORT":
            direction_votes["SHORT"] += triple_st["score"] / 100
            reasons.extend(triple_st["signals"])

        # TTD votes
        if ttd["direction"] == "LONG":
            direction_votes["LONG"] += ttd["score"] / 100
            reasons.extend(ttd["signals"])
        elif ttd["direction"] == "SHORT":
            direction_votes["SHORT"] += ttd["score"] / 100
            reasons.extend(ttd["signals"])

        # VWAP votes
        if vwap_div["direction"] == "LONG":
            direction_votes["LONG"] += vwap_div["score"] / 100
            reasons.extend(vwap_div["signals"])
        elif vwap_div["direction"] == "SHORT":
            direction_votes["SHORT"] += vwap_div["score"] / 100
            reasons.extend(vwap_div["signals"])

        # Determine direction
        if direction_votes["LONG"] > direction_votes["SHORT"] and direction_votes["LONG"] >= 1.5:
            direction = "LONG"
            total_score = int(direction_votes["LONG"] * 40)
        elif direction_votes["SHORT"] > direction_votes["LONG"] and direction_votes["SHORT"] >= 1.5:
            direction = "SHORT"
            total_score = int(direction_votes["SHORT"] * 40)
        else:
            direction = "NEUTRAL"
            total_score = 50

        return {
            "direction": direction,
            "score": min(total_score, 100),
            "triple_supertrend": triple_st,
            "ttd": ttd,
            "vwap_divergence": vwap_div,
            "reasons": reasons,
            "signals_count": sum(1 for s in [triple_st, ttd, vwap_div] if s.get("direction") != "NEUTRAL"),
        }
