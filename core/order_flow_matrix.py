# -*- coding: utf-8 -*-
"""
Institutional Order Flow Imbalance Matrix PRO
استخراج شده از Pine Script
شامل:
1. HTF Structural Levels (High/Low تایم‌فریم بالاتر)
2. Volume Validated Imbalance Zones (FVG + Volume Spike)
3. ATR Trend Ribbon (Dynamic Trend Direction)
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class OrderFlowMatrix:
    """
    Institutional Order Flow Imbalance Matrix PRO
    ترکیب 3 سیستم برای تشخیص جریان سفارشات نهادی
    """

    def __init__(self):
        # HTF Settings
        self.htf_period = 4  # 4h candles for HTF levels
        # Imbalance Settings
        self.imb_volume_threshold = 1.2  # volume spike factor
        self.imb_lookback = 20  # SMA period for avg volume
        # Ribbon Settings
        self.ribbon_atr_len = 14
        self.ribbon_atr_mult = 2.0

    def analyze_htf_levels(self, candles_4h, current_price):
        """
        تحلیل سطوح High/Low تایم‌فریم بالاتر (4H)
        سطح قبلی که شکسته نشده = مقاومت/حمایت کلیدی
        """
        if not candles_4h or len(candles_4h) < 3:
            return {"status": "no_data", "score": 50, "signals": []}

        # Previous HTF high/low (candles[-2] = previous completed 4H candle)
        prev_htf = candles_4h[-2] if len(candles_4h) >= 2 else candles_4h[-1]
        htf_high = prev_htf["high"]
        htf_low = prev_htf["low"]

        signals = []
        score = 50
        direction = "NEUTRAL"

        # Check if price is near HTF levels
        proximity_pct = 0.005  # 0.5%
        price = current_price

        # Near HTF High (resistance)
        dist_to_high = abs(price - htf_high) / htf_high
        dist_to_low = abs(price - htf_low) / htf_low

        if dist_to_high < proximity_pct:
            signals.append(f"🔴 نزدیک HTF High: {htf_high:.4f} (مقاومت کلیدی)")
            score = 35  # Bearish - near resistance
            direction = "SHORT"
        elif dist_to_low < proximity_pct:
            signals.append(f"🟢 نزدیک HTF Low: {htf_low:.4f} (حمایت کلیدی)")
            score = 65  # Bullish - near support
            direction = "LONG"
        else:
            # Price between levels
            mid = (htf_high + htf_low) / 2
            if price > mid:
                signals.append(f"📈 بالای میانه HTF: حباب صعودی")
                score = 55
            else:
                signals.append(f"📉 زیر میانه HTF: حباب نزولی")
                score = 45

        # Check if HTF levels were broken recently
        recent_4h = candles_4h[-6:] if len(candles_4h) >= 6 else candles_4h
        high_broken = any(c["high"] > htf_high for c in recent_4h[:-1])
        low_broken = any(c["low"] < htf_low for c in recent_4h[:-1])

        if high_broken and not low_broken:
            signals.append("🚀 HTF High شکسته شد - صعودی قوی!")
            score = 75
            direction = "LONG"
        elif low_broken and not high_broken:
            signals.append("🔻 HTF Low شکسته شد - نزولی قوی!")
            score = 25
            direction = "SHORT"

        return {
            "status": "active",
            "htf_high": htf_high,
            "htf_low": htf_low,
            "score": score,
            "signals": signals,
            "direction": direction,
        }

    def detect_imbalance_zones(self, candles):
        """
        تشخیص Volume Validated Imbalance Zones
        Fair Value Gap (FVG) با حجم بالا = منطقه نهادی
        
        Bullish Imbalance: low[0] > high[2] (gap صعودی)
        Bearish Imbalance: high[0] < low[2] (gap نزولی)
        """
        if len(candles) < 5:
            return {"zones": [], "score": 50, "signals": []}

        # Calculate average volume
        volumes = [c["volume"] for c in candles[-self.imb_lookback:]]
        avg_vol = np.mean(volumes) if volumes else 0

        signals = []
        zones = []
        bullish_count = 0
        bearish_count = 0

        # Check recent candles for imbalance
        check_range = min(10, len(candles) - 3)
        for i in range(-check_range, -2):
            if i + 2 >= 0:
                continue

            c0 = candles[i]      # current
            c2 = candles[i + 2]  # 2 candles ago

            vol_spike = c0["volume"] > (avg_vol * self.imb_volume_threshold)

            if not vol_spike:
                continue

            # Bullish Imbalance: current low > high 2 candles ago
            if c0["low"] > c2["high"]:
                zone = {
                    "type": "bullish",
                    "top": c0["low"],
                    "bottom": c2["high"],
                    "volume": c0["volume"],
                    "avg_volume": avg_vol,
                    "index": i,
                }
                zones.append(zone)
                bullish_count += 1

            # Bearish Imbalance: current high < low 2 candles ago
            elif c0["high"] < c2["low"]:
                zone = {
                    "type": "bearish",
                    "top": c2["low"],
                    "bottom": c0["high"],
                    "volume": c0["volume"],
                    "avg_volume": avg_vol,
                    "index": i,
                }
                zones.append(zone)
                bearish_count += 1

        # Score based on zones
        if bullish_count > bearish_count:
            score = 60 + min(bullish_count * 5, 25)
            signals.append(f"🟢 {bullish_count} Bullish Imbalance Zone (حجم×{self.imb_volume_threshold})")
            direction = "LONG"
        elif bearish_count > bullish_count:
            score = 40 - min(bearish_count * 5, 25)
            signals.append(f"🔴 {bearish_count} Bearish Imbalance Zone (حجم×{self.imb_volume_threshold})")
            direction = "SHORT"
        else:
            score = 50
            signals.append("⚪ هیچ Imbalance Zone فعالی نیست")
            direction = "NEUTRAL"

        # Check if price is inside any zone (magnet effect)
        current_price = candles[-1]["close"]
        inside_zone = False
        for z in zones[-3:]:  # check recent zones
            if z["bottom"] <= current_price <= z["top"]:
                inside_zone = True
                if z["type"] == "bullish":
                    signals.append(f"💎 قیمت داخل Bullish Zone: {z['bottom']:.4f}-{z['top']:.4f}")
                else:
                    signals.append(f"💎 قیمت داخل Bearish Zone: {z['bottom']:.4f}-{z['top']:.4f}")
                break

        return {
            "zones": zones[-5:],  # keep last 5
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "inside_zone": inside_zone,
            "score": score,
            "signals": signals,
            "direction": direction,
        }

    def analyze_atr_ribbon(self, candles):
        """
        Institutional Dynamic ATR Trend Ribbon
        تشخیص جهت ترند با ATR Trailing Stop
        
        trend_dir = 1: صعودی (price above stop)
        trend_dir = -1: نزولی (price below stop)
        """
        if len(candles) < self.ribbon_atr_len + 5:
            return {"trend_dir": 0, "score": 50, "signals": []}

        # Calculate ATR
        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)

        # SMA of TR = ATR
        atr = []
        for i in range(self.ribbon_atr_len - 1, len(tr_values)):
            atr.append(np.mean(tr_values[i - self.ribbon_atr_len + 1 : i + 1]))

        if not atr:
            return {"trend_dir": 0, "score": 50, "signals": []}

        # Calculate trend direction
        trend_dir = 1  # start bullish
        trend_stop = None

        # Align with candles
        start_idx = len(candles) - len(atr) - 1

        for i in range(len(atr)):
            idx = start_idx + i + 1
            if idx >= len(candles):
                break

            src_close = candles[idx]["close"]
            atr_val = atr[i]

            upper_stop = src_close - (atr_val * self.ribbon_atr_mult)
            lower_stop = src_close + (atr_val * self.ribbon_atr_mult)

            if trend_stop is None:
                trend_stop = upper_stop
                continue

            if trend_dir == 1:
                if src_close < trend_stop:
                    trend_dir = -1
                    trend_stop = lower_stop
                else:
                    trend_stop = max(trend_stop, upper_stop)
            else:
                if src_close > trend_stop:
                    trend_dir = 1
                    trend_stop = upper_stop
                else:
                    trend_stop = min(trend_stop, lower_stop)

        signals = []
        if trend_dir == 1:
            score = 65
            signals.append("🟢 ATR Ribbon: ترند صعودی نهادی")
        elif trend_dir == -1:
            score = 35
            signals.append("🔴 ATR Ribbon: ترند نزولی نهادی")
        else:
            score = 50
            signals.append("⚪ ATR Ribbon: ترند خنثی")

        # Check distance from stop (momentum strength)
        current_price = candles[-1]["close"]
        if trend_stop:
            dist_from_stop = abs(current_price - trend_stop) / current_price * 100
            if dist_from_stop > 2:
                signals.append(f"💪 فاصله از Stop: {dist_from_stop:.1f}% (ترند قوی)")
                score += 5 if trend_dir == 1 else -5

        return {
            "trend_dir": trend_dir,
            "trend_stop": trend_stop,
            "score": min(max(score, 0), 100),
            "signals": signals,
            "direction": "LONG" if trend_dir == 1 else "SHORT" if trend_dir == -1 else "NEUTRAL",
        }

    def analyze(self, candles_1h, candles_4h=None, current_price=None):
        """
        تحلیل کامل Order Flow Imbalance Matrix
        """
        if current_price is None and candles_1h:
            current_price = candles_1h[-1]["close"]

        # 1. HTF Structural Levels
        htf = self.analyze_htf_levels(candles_4h, current_price) if candles_4h else {"score": 50, "signals": [], "direction": "NEUTRAL"}

        # 2. Volume Imbalance Zones
        imb = self.detect_imbalance_zones(candles_1h) if candles_1h else {"score": 50, "signals": [], "direction": "NEUTRAL", "zones": []}

        # 3. ATR Trend Ribbon
        ribbon = self.analyze_atr_ribbon(candles_1h) if candles_1h else {"score": 50, "signals": [], "direction": "NEUTRAL"}

        # Combine votes
        direction_votes = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
        reasons = []
        total_score = 50

        components = [
            ("htf", htf, 1.0),
            ("imbalance", imb, 1.2),
            ("ribbon", ribbon, 1.0),
        ]

        scores = []
        for name, comp, weight in components:
            comp_score = comp.get("score", 50)
            scores.append((name, comp_score))
            
            comp_dir = comp.get("direction", "NEUTRAL")
            if comp_dir == "LONG":
                direction_votes["LONG"] += weight
                reasons.extend(comp.get("signals", [])[:2])
            elif comp_dir == "SHORT":
                direction_votes["SHORT"] += weight
                reasons.extend(comp.get("signals", [])[:2])

        # Determine direction
        total_score = sum(s[1] for s in scores) / len(scores) if scores else 50

        if direction_votes["LONG"] > direction_votes["SHORT"] and direction_votes["LONG"] >= 2:
            direction = "LONG"
        elif direction_votes["SHORT"] > direction_votes["LONG"] and direction_votes["SHORT"] >= 2:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        # Strong confirmation: all 3 agree
        all_agree = (htf.get("direction") == imb.get("direction") == ribbon.get("direction") != "NEUTRAL")

        return {
            "direction": direction,
            "score": int(total_score),
            "htf_levels": htf,
            "imbalance_zones": imb,
            "atr_ribbon": ribbon,
            "reasons": reasons,
            "all_agree": all_agree,
            "signals_count": sum(1 for c in [htf, imb, ribbon] if c.get("direction") != "NEUTRAL"),
        }
