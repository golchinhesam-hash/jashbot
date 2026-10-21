# -*- coding: utf-8 -*-
"""
Pre-Movement Detector - تشخیص حرکت قبل از اتفاق
سیستمی که پمپ/دامپ رو قبل از اینکه RSI یا اندیکاتورهای لگینگ واکنش نشون بدن، تشخیص میده

تکنیک‌ها:
1. RSI Divergence (کلاسیک‌ترین سیگنال برگشت)
2. Volume Climax (حجم نهایی = پایان حرکت)
3. Delta Divergence (فشار خرید/فروش vs قیمت)
4. Order Book Imbalance Shift (تغییر ناگهانی تعادل)
5. Hidden Divergence (تایید روند)
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class PreMovementDetector:
    """تشخیص حرکت قبل از اتفاق - قبل از RSI و اندیکاتورهای لگینگ"""

    def __init__(self):
        self.lookback = 50  # تعداد کندل برای تحلیل

    def calculate_rsi(self, closes, period=14):
        """محاسبه RSI"""
        if len(closes) < period + 1:
            return []

        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.convolve(gains, np.ones(period)/period, mode='valid')
        avg_loss = np.convolve(losses, np.ones(period)/period, mode='valid')

        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def detect_rsi_divergence(self, candles):
        """
        تشخیص واگرایی RSI

        Bullish Divergence: قیمت Lower Low ولی RSI Higher Low → برگشت صعودی
        Bearish Divergence: قیمت Higher High ولی RSI Lower High → برگشت نزولی

        Hidden Bullish: قیمت Higher Low ولی RSI Lower Low → ادامه صعود
        Hidden Bearish: قیمت Lower High ولی RSI Higher High → ادامه نزول
        """
        if not candles or len(candles) < 30:
            return {"type": "none", "strength": 0, "reasons": []}

        closes = np.array([c["close"] for c in candles])
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])

        rsi = self.calculate_rsi(closes)
        if len(rsi) < 20:
            return {"type": "none", "strength": 0, "reasons": []}

        # هماهنگ کردن اندیس‌ها (RSI از کندل 14 شروع میشه)
        offset = len(closes) - len(rsi)
        rsi_highs = []
        rsi_lows = []
        price_highs = []
        price_lows = []

        # پیدا کردن Swing Points در 20 کندل اخیر
        recent_len = min(20, len(rsi))
        recent_rsi = rsi[-recent_len:]
        recent_closes = closes[-recent_len:]
        recent_highs = highs[-recent_len:]
        recent_lows = lows[-recent_len:]

        # پیدا کردن Swing Highs/Lows در RSI
        rsi_swing_highs = []
        rsi_swing_lows = []
        for i in range(2, len(recent_rsi) - 2):
            # Swing High
            if recent_rsi[i] > recent_rsi[i-1] and recent_rsi[i] > recent_rsi[i-2] and \
               recent_rsi[i] > recent_rsi[i+1] and recent_rsi[i] > recent_rsi[i+2]:
                rsi_swing_highs.append((i, recent_rsi[i]))
            # Swing Low
            if recent_rsi[i] < recent_rsi[i-1] and recent_rsi[i] < recent_rsi[i-2] and \
               recent_rsi[i] < recent_rsi[i+1] and recent_rsi[i] < recent_rsi[i+2]:
                rsi_swing_lows.append((i, recent_rsi[i]))

        # پیدا کردن Swing Highs/Lows در قیمت
        price_swing_highs = []
        price_swing_lows = []
        for i in range(2, len(recent_highs) - 2):
            if recent_highs[i] > recent_highs[i-1] and recent_highs[i] > recent_highs[i-2] and \
               recent_highs[i] > recent_highs[i+1] and recent_highs[i] > recent_highs[i+2]:
                price_swing_highs.append((i, recent_highs[i]))
            if recent_lows[i] < recent_lows[i-1] and recent_lows[i] < recent_lows[i-2] and \
               recent_lows[i] < recent_lows[i+1] and recent_lows[i] < recent_lows[i+2]:
                price_swing_lows.append((i, recent_lows[i]))

        reasons = []
        divergence_type = "none"
        strength = 0

        # Bullish Divergence: Price LL, RSI HL
        if len(price_swing_lows) >= 2 and len(rsi_swing_lows) >= 2:
            last_price_low = price_swing_lows[-1]
            prev_price_low = price_swing_lows[-2]
            last_rsi_low = rsi_swing_lows[-1] if len(rsi_swing_lows) >= len(price_swing_lows) else rsi_swing_lows[-1]
            prev_rsi_low = rsi_swing_lows[-2] if len(rsi_swing_lows) >= 2 else None

            if prev_rsi_low and last_price_low[1] < prev_price_low[1] and last_rsi_low[1] > prev_rsi_low[1]:
                divergence_type = "bullish_divergence"
                strength = 80
                reasons.append(f"🟢 Bullish Divergence: قیمت Lower Low ولی RSI Higher Low")
                reasons.append(f"   قیمت: {prev_price_low[1]:.2f} → {last_price_low[1]:.2f}")
                reasons.append(f"   RSI: {prev_rsi_low[1]:.1f} → {last_rsi_low[1]:.1f}")

        # Bearish Divergence: Price HH, RSI LH
        if len(price_swing_highs) >= 2 and len(rsi_swing_highs) >= 2:
            last_price_high = price_swing_highs[-1]
            prev_price_high = price_swing_highs[-2]
            last_rsi_high = rsi_swing_highs[-1] if len(rsi_swing_highs) >= len(price_swing_highs) else rsi_swing_highs[-1]
            prev_rsi_high = rsi_swing_highs[-2] if len(rsi_swing_highs) >= 2 else None

            if prev_rsi_high and last_price_high[1] > prev_price_high[1] and last_rsi_high[1] < prev_rsi_high[1]:
                divergence_type = "bearish_divergence"
                strength = 80
                reasons.append(f"🔴 Bearish Divergence: قیمت Higher High ولی RSI Lower High")
                reasons.append(f"   قیمت: {prev_price_high[1]:.2f} → {last_price_high[1]:.2f}")
                reasons.append(f"   RSI: {prev_rsi_high[1]:.1f} → {last_rsi_high[1]:.1f}")

        # Hidden Bullish: Price HL, RSI LL (تایید ادامه صعود)
        if divergence_type == "none" and len(price_swing_lows) >= 2 and len(rsi_swing_lows) >= 2:
            last_price_low = price_swing_lows[-1]
            prev_price_low = price_swing_lows[-2]
            last_rsi_low = rsi_swing_lows[-1]
            prev_rsi_low = rsi_swing_lows[-2] if len(rsi_swing_lows) >= 2 else None

            if prev_rsi_low and last_price_low[1] > prev_price_low[1] and last_rsi_low[1] < prev_rsi_low[1]:
                divergence_type = "hidden_bullish"
                strength = 60
                reasons.append(f"🟢 Hidden Bullish: قیمت Higher Low ولی RSI Lower Low → ادامه صعود")

        # Hidden Bearish: Price LH, RSI HH (تایید ادامه نزول)
        if divergence_type == "none" and len(price_swing_highs) >= 2 and len(rsi_swing_highs) >= 2:
            last_price_high = price_swing_highs[-1]
            prev_price_high = price_swing_highs[-2]
            last_rsi_high = rsi_swing_highs[-1]
            prev_rsi_high = rsi_swing_highs[-2] if len(rsi_swing_highs) >= 2 else None

            if prev_rsi_high and last_price_high[1] < prev_price_high[1] and last_rsi_high[1] > prev_rsi_high[1]:
                divergence_type = "hidden_bearish"
                strength = 60
                reasons.append(f"🔴 Hidden Bearish: قیمت Lower High ولی RSI Higher High → ادامه نزول")

        # RSI Extreme levels (با واگرایی قوی‌تر میشه)
        current_rsi = rsi[-1]
        if current_rsi < 30 and "bullish" in divergence_type:
            strength += 10
            reasons.append(f"RSI Oversold: {current_rsi:.1f} (زیر 30)")
        elif current_rsi > 70 and "bearish" in divergence_type:
            strength += 10
            reasons.append(f"RSI Overbought: {current_rsi:.1f} (بالای 70)")

        return {
            "type": divergence_type,
            "strength": min(strength, 100),
            "current_rsi": current_rsi,
            "reasons": reasons,
            "direction": "LONG" if "bullish" in divergence_type else "SHORT" if "bearish" in divergence_type else "NEUTRAL",
        }

    def detect_volume_climax(self, candles):
        """
        تشخیص Volume Climax
        حجم خیلی بالا معمولاً نشون‌دهنده پایان حرکت فعلی و شروع حرکت جدیده
        """
        if not candles or len(candles) < 20:
            return {"climax": False, "type": "none", "strength": 0, "reasons": []}

        volumes = np.array([c["volume"] for c in candles])
        closes = np.array([c["close"] for c in candles])
        opens = np.array([c["open"] for c in candles])

        avg_vol = np.mean(volumes[:-5])  # میانگین بدون 5 کندل آخر
        std_vol = np.std(volumes[:-5])
        current_vol = volumes[-1]
        prev_vol = volumes[-2]

        reasons = []
        climax_type = "none"
        strength = 0

        # Volume Climax detection
        if current_vol > avg_vol + 3 * std_vol:  # 3 sigma
            strength = 70
            current_close = closes[-1]
            current_open = opens[-1]

            if current_close > current_open:
                climax_type = "buying_climax"
                reasons.append(f"🟢 Buying Climax: حجم {current_vol/avg_vol:.1f}x میانگین")
                # اگه کندل صعودی با حجم خیلی بالا = احتمال distribution
                if current_close > closes[-2] * 1.02:  # 2% صعود
                    reasons.append("⚠️ احتمال Distribution: نهنگ‌ها دارن می‌فروشن")
                    climax_type = "potential_dump"
            else:
                climax_type = "selling_climax"
                reasons.append(f"🔴 Selling Climax: حجم {current_vol/avg_vol:.1f}x میانگین")
                # اگه کندل نزولی با حجم خیلی بالا = احتمال accumulation
                if current_close < closes[-2] * 0.98:  # 2% نزول
                    reasons.append("🟢 احتمال Accumulation: نهنگ‌ها دارن می‌خرن")
                    climax_type = "potential_pump"

        elif current_vol > avg_vol + 2 * std_vol:  # 2 sigma
            strength = 50
            if current_vol > prev_vol * 2:
                reasons.append(f"حجم ناگهانی: {current_vol/avg_vol:.1f}x میانگین")

        # Volume divergence (حجم کم در حرکت = ضعیف)
        last_3_change = abs(closes[-1] - closes[-4]) / closes[-4] * 100
        last_3_vol = np.mean(volumes[-3:])
        if last_3_change > 3 and last_3_vol < avg_vol * 0.7:
            reasons.append("⚠️ Volume Divergence: حرکت قوی با حجم پایین = ضعیف")
            strength = max(strength, 40)

        return {
            "climax": strength > 0,
            "type": climax_type,
            "strength": min(strength, 100),
            "volume_ratio": current_vol / avg_vol if avg_vol > 0 else 0,
            "reasons": reasons,
            "direction": "SHORT" if climax_type == "potential_dump" else "LONG" if climax_type == "potential_pump" else "NEUTRAL",
        }

    def detect_delta_divergence(self, candles):
        """
        تشخیص Delta Divergence
        Delta = حجم خریدار - حجم فروشنده
        وقتی Delta خلاف جهت قیمت حرکت می‌کنه = واگرایی
        """
        if not candles or len(candles) < 20:
            return {"divergence": False, "type": "none", "strength": 0, "reasons": []}

        # محاسبه delta تخمینی از کندل‌ها
        # delta positive = بیشتر خرید (close نزدیک high)
        # delta negative = بیشتر فروش (close نزدیک low)
        deltas = []
        for c in candles:
            body = c["close"] - c["open"]
            range_c = c["high"] - c["low"]
            if range_c == 0:
                delta = 0
            else:
                # delta = volume * (close_position_in_range - 0.5) * 2
                close_pos = (c["close"] - c["low"]) / range_c
                delta = c["volume"] * (close_pos - 0.5) * 2
            deltas.append(delta)

        deltas = np.array(deltas)
        closes = np.array([c["close"] for c in candles])

        # Cumulative Delta
        cvd = np.cumsum(deltas)

        # چک کردن 10 کندل اخیر
        recent_cvd = cvd[-10:]
        recent_closes = closes[-10:]

        reasons = []
        div_type = "none"
        strength = 0

        # Bullish Delta Divergence: قیمت پایین‌تر ولی CVD بالاتر
        if recent_closes[-1] < recent_closes[0] and recent_cvd[-1] > recent_cvd[0]:
            div_type = "bullish_delta_div"
            strength = 75
            reasons.append("🟢 Delta Bullish Divergence: قیمت نزولی ولی فشار خرید در حال افزایش")
            reasons.append("   نهنگ‌ها در حال جمع‌آوری زیر قیمت")

        # Bearish Delta Divergence: قیمت بالاتر ولی CVD پایین‌تر
        elif recent_closes[-1] > recent_closes[0] and recent_cvd[-1] < recent_cvd[0]:
            div_type = "bearish_delta_div"
            strength = 75
            reasons.append("🔴 Delta Bearish Divergence: قیمت صعودی ولی فشار فروش در حال افزایش")
            reasons.append("   نهنگ‌ها در حال Distribution بالای قیمت")

        # Delta Spike
        last_delta = deltas[-1]
        avg_delta = np.mean(deltas[:-5])
        std_delta = np.std(deltas[:-5])

        if abs(last_delta) > abs(avg_delta) + 3 * std_delta:
            strength += 10
            if last_delta > 0:
                reasons.append(f"🟢 Delta Spike: فشار خرید شدید ({last_delta/1e6:.1f}M)")
            else:
                reasons.append(f"🔴 Delta Spike: فشار فروش شدید ({last_delta/1e6:.1f}M)")

        return {
            "divergence": div_type != "none",
            "type": div_type,
            "strength": min(strength, 100),
            "cvd_trend": "rising" if recent_cvd[-1] > recent_cvd[0] else "falling",
            "reasons": reasons,
            "direction": "LONG" if "bullish" in div_type else "SHORT" if "bearish" in div_type else "NEUTRAL",
        }

    def detect_ob_imbalance_shift(self, order_book, current_price):
        """
        تشخیص تغییر ناگهانی تعادل order book
        وقتی bid/ask ratio ناگهانی تغییر می‌کنه = نهنگ وارد شده
        """
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            return {"shift": False, "type": "none", "strength": 0, "reasons": []}

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        if not bids or not asks:
            return {"shift": False, "type": "none", "strength": 0, "reasons": []}

        # محاسبه حجم در 1% اطراف قیمت
        price_range = current_price * 0.01  # 1%

        bid_volume_near = 0
        for price, qty in bids[:20]:
            p = float(price)
            if current_price - p <= price_range:
                bid_volume_near += float(qty) * p

        ask_volume_near = 0
        for price, qty in asks[:20]:
            p = float(price)
            if p - current_price <= price_range:
                ask_volume_near += float(qty) * p

        total_near = bid_volume_near + ask_volume_near
        if total_near == 0:
            return {"shift": False, "type": "none", "strength": 0, "reasons": []}

        bid_ratio = bid_volume_near / total_near
        ask_ratio = ask_volume_near / total_near

        reasons = []
        shift_type = "none"
        strength = 0

        # Extreme imbalance
        if bid_ratio > 0.7:
            shift_type = "heavy_buying"
            strength = int((bid_ratio - 0.5) * 200)
            reasons.append(f"🟢 Heavy Buying Pressure: {bid_ratio*100:.0f}% خرید در 1% اطراف قیمت")
            reasons.append(f"   حجم خرید: ${bid_volume_near/1e6:.1f}M vs فروش: ${ask_volume_near/1e6:.1f}M")
        elif ask_ratio > 0.7:
            shift_type = "heavy_selling"
            strength = int((ask_ratio - 0.5) * 200)
            reasons.append(f"🔴 Heavy Selling Pressure: {ask_ratio*100:.0f}% فروش در 1% اطراف قیمت")
            reasons.append(f"   حجم فروش: ${ask_volume_near/1e6:.1f}M vs خرید: ${bid_volume_near/1e6:.1f}M")

        return {
            "shift": shift_type != "none",
            "type": shift_type,
            "strength": min(strength, 100),
            "bid_ratio": bid_ratio,
            "ask_ratio": ask_ratio,
            "reasons": reasons,
            "direction": "LONG" if shift_type == "heavy_buying" else "SHORT" if shift_type == "heavy_selling" else "NEUTRAL",
        }

    def analyze_pre_movement(self, candles, order_book=None, current_price=None):
        """
        تحلیل کامل قبل از حرکت
        ترکیب همه سیگنال‌ها برای تشخیص زودتر
        """
        if not current_price and candles:
            current_price = candles[-1]["close"]

        # 1. RSI Divergence
        rsi_div = self.detect_rsi_divergence(candles)

        # 2. Volume Climax
        vol_climax = self.detect_volume_climax(candles)

        # 3. Delta Divergence
        delta_div = self.detect_delta_divergence(candles)

        # 4. Order Book Imbalance
        ob_shift = self.detect_ob_imbalance_shift(order_book, current_price) if order_book else {"shift": False}

        # ترکیب نتایج
        all_signals = [rsi_div, vol_climax, delta_div, ob_shift]

        # شمارش آرا
        direction_votes = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
        total_strength = 0
        reasons = []

        for sig in all_signals:
            if sig.get("direction") == "LONG":
                direction_votes["LONG"] += sig.get("strength", 0) / 100
                total_strength += sig.get("strength", 0)
            elif sig.get("direction") == "SHORT":
                direction_votes["SHORT"] += sig.get("strength", 0) / 100
                total_strength += sig.get("strength", 0)
            reasons.extend(sig.get("reasons", []))

        # تعیین جهت نهایی
        direction = "NEUTRAL"
        confidence = 0

        if direction_votes["LONG"] > direction_votes["SHORT"] and direction_votes["LONG"] >= 1.0:
            direction = "LONG"
            confidence = int(direction_votes["LONG"] * 50)
        elif direction_votes["SHORT"] > direction_votes["LONG"] and direction_votes["SHORT"] >= 1.0:
            direction = "SHORT"
            confidence = int(direction_votes["SHORT"] * 50)

        return {
            "direction": direction,
            "confidence": min(confidence, 100),
            "rsi_divergence": rsi_div,
            "volume_climax": vol_climax,
            "delta_divergence": delta_div,
            "ob_shift": ob_shift,
            "reasons": reasons,
            "signals_count": sum(1 for s in all_signals if s.get("direction") != "NEUTRAL"),
        }
