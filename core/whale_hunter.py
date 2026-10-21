# -*- coding: utf-8 -*-
"""
Whale Hunter - اسکنر پیشرفته نهنگ‌ها
تشخیص:
1. دیوارهای سفارش بزرگ (Order Book Walls)
2. سطوح لیکویید (Liquidation Levels)
3. پمپ/دامپ قبل از اتفاق (Pre-Pump/Dump Detection)
4. نفوذ به تارگت‌های نهنگ (Whale Target Infiltration)
"""

import logging
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class WhaleHunter:
    """شکارچی نهنگ - اسکنر پیشرفته"""

    def __init__(self):
        # حداقل حجم برای دیوار سفارش (به USDT)
        self.wall_threshold_usdt = 500_000  # 500K USDT
        self.large_wall_threshold = 1_000_000  # 1M USDT
        self.mega_wall_threshold = 5_000_000  # 5M USDT

    def analyze_order_book_for_whales(self, order_book, current_price, symbol=""):
        """
        تحلیل عمیق order book برای پیدا کردن تارگت‌های نهنگ

        Returns: {
            "bid_walls": [...],      # دیوارهای خرید
            "ask_walls": [...],      # دیوارهای فروش
            "liquidation_zones": [...],  # نزدیک‌ترین سطوح لیکویید
            "whale_pressure": str,   # buy/sell/neutral
            "support_wall": dict,    # قوی‌ترین دیوار حمایت
            "resistance_wall": dict, # قوی‌ترین دیوار مقاومت
            "score": int,            # 0-100
            "reasons": [],
        }
        """
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            return self._empty_result()

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        if not bids or not asks:
            return self._empty_result()

        reasons = []
        bid_walls = []
        ask_walls = []

        # پیدا کردن دیوارهای خرید (BID walls)
        for i, (price, qty) in enumerate(bids[:20]):  # 20 سطح اول
            price = float(price)
            qty = float(qty)
            value_usdt = price * qty

            if value_usdt >= self.wall_threshold_usdt:
                wall = {
                    "price": price,
                    "qty": qty,
                    "value_usdt": value_usdt,
                    "distance_pct": (current_price - price) / current_price * 100,
                    "level": self._classify_wall(value_usdt),
                }
                bid_walls.append(wall)

        # پیدا کردن دیوارهای فروش (ASK walls)
        for i, (price, qty) in enumerate(asks[:20]):
            price = float(price)
            qty = float(qty)
            value_usdt = price * qty

            if value_usdt >= self.wall_threshold_usdt:
                wall = {
                    "price": price,
                    "qty": qty,
                    "value_usdt": value_usdt,
                    "distance_pct": (price - current_price) / current_price * 100,
                    "level": self._classify_wall(value_usdt),
                }
                ask_walls.append(wall)

        # مرتب‌سازی بر اساس ارزش
        bid_walls.sort(key=lambda x: x['value_usdt'], reverse=True)
        ask_walls.sort(key=lambda x: x['value_usdt'], reverse=True)

        # قوی‌ترین دیوارها
        support_wall = bid_walls[0] if bid_walls else None
        resistance_wall = ask_walls[0] if ask_walls else None

        # محاسبه فشار نهنگ
        total_bid_value = sum(w['value_usdt'] for w in bid_walls)
        total_ask_value = sum(w['value_usdt'] for w in ask_walls)

        whale_pressure = "neutral"
        score = 50

        if total_bid_value > total_ask_value * 2:
            whale_pressure = "buy"
            score = 70 + min(30, int((total_bid_value / total_ask_value - 1) * 10))
            reasons.append(f"فشار خرید نهنگی قوی: ${total_bid_value/1e6:.1f}M vs ${total_ask_value/1e6:.1f}M")
        elif total_ask_value > total_bid_value * 2:
            whale_pressure = "sell"
            score = 70 + min(30, int((total_ask_value / total_bid_value - 1) * 10))
            reasons.append(f"فشار فروش نهنگی قوی: ${total_ask_value/1e6:.1f}M vs ${total_bid_value/1e6:.1f}M")
        else:
            reasons.append("تعادل نسبی بین خریدار و فروشنده نهنگ")

        # هشدار دیوارهای خیلی بزرگ
        if support_wall and support_wall['level'] == 'mega':
            reasons.append(f"🐋 MEGA WALL خرید: ${support_wall['value_usdt']/1e6:.1f}M @ {support_wall['price']:.2f}")
            score += 10
        elif support_wall and support_wall['level'] == 'large':
            reasons.append(f"🐋 دیوار بزرگ خرید: ${support_wall['value_usdt']/1e6:.1f}M @ {support_wall['price']:.2f}")
            score += 5

        if resistance_wall and resistance_wall['level'] == 'mega':
            reasons.append(f"🐋 MEGA WALL فروش: ${resistance_wall['value_usdt']/1e6:.1f}M @ {resistance_wall['price']:.2f}")
            score -= 10
        elif resistance_wall and resistance_wall['level'] == 'large':
            reasons.append(f"🐋 دیوار بزرگ فروش: ${resistance_wall['value_usdt']/1e6:.1f}M @ {resistance_wall['price']:.2f}")
            score -= 5

        # محاسبه سطوح لیکویید
        liquidation_zones = self._calculate_liquidation_zones(
            current_price, bid_walls, ask_walls
        )

        return {
            "bid_walls": bid_walls[:5],
            "ask_walls": ask_walls[:5],
            "liquidation_zones": liquidation_zones,
            "whale_pressure": whale_pressure,
            "support_wall": support_wall,
            "resistance_wall": resistance_wall,
            "score": min(100, max(0, score)),
            "reasons": reasons,
            "total_bid_value": total_bid_value,
            "total_ask_value": total_ask_value,
        }

    def detect_pump_dump_setup(self, candles, order_book=None, trades=None):
        """
        تشخیص ستاپ پمپ یا دامپ قبل از اتفاق

        علائم پمپ:
        - جمع‌آوری نقدینگی زیر (sweep lows)
        - دیوار خرید قوی در order book
        - حجم پایین در پولبک
        - Wick‌های بلند در کف

        علائم دامپ:
        - جمع‌آوری نقدینگی بالا (sweep highs)
        - دیوار فروش قوی
        - حجم بالا در ریجکشن
        """
        if not candles or len(candles) < 20:
            return {"setup": "none", "confidence": 0, "reasons": []}

        reasons = []
        pump_score = 0
        dump_score = 0

        # تحلیل 10 کندل اخیر
        recent = candles[-10:]
        volumes = [c['volume'] for c in recent]
        avg_volume = np.mean(volumes[:-3]) if len(volumes) > 3 else np.mean(volumes)
        current_volume = volumes[-1] if volumes else 0

        # تحلیل wick‌ها
        lower_wicks = []
        upper_wicks = []
        for c in recent:
            body = abs(c['close'] - c['open'])
            if body == 0:
                body = 0.0001
            lower_wick = min(c['open'], c['close']) - c['low']
            upper_wick = c['high'] - max(c['open'], c['close'])
            lower_wicks.append(lower_wick / body)
            upper_wicks.append(upper_wick / body)

        # علائم پمپ
        # 1. Wick پایینی بلند = جمع‌آوری نقدینگی
        if lower_wicks and np.mean(lower_wicks[-3:]) > 2.0:
            pump_score += 20
            reasons.append("Wick پایینی بلند: نهنگ‌ها داره نقدینگی جمع می‌کنن (Liquidity Grab)")

        # 2. حجم پایین در ریزش = lack of selling pressure
        if current_volume < avg_volume * 0.7:
            pump_score += 15
            reasons.append("حجم پایین در ریزش: فشار فروش ضعیفه")

        # 3. کندل آخر صعودی با حجم
        last = candles[-1]
        if last['close'] > last['open'] and last['volume'] > avg_volume * 1.5:
            pump_score += 15
            reasons.append("کندل صعودی با حجم بالا: شروع حرکت صعودی")

        # علائم دامپ
        # 1. Wick بالایی بلند
        if upper_wicks and np.mean(upper_wicks[-3:]) > 2.0:
            dump_score += 20
            reasons.append("Wick بالایی بلند: نهنگ‌ها داره نقدینگی بالا جمع می‌کنن")

        # 2. حجم بالا در صعود = distribution
        if last['close'] > last['open'] and last['volume'] > avg_volume * 2.0:
            dump_score += 15
            reasons.append("حجم خیلی بالا در صعود: احتمال distribution نهنگ‌ها")

        # 3. ریجکشن از بالا
        if last['close'] < last['high'] * 0.98 and last['volume'] > avg_volume * 1.5:
            dump_score += 15
            reasons.append("ریجکشن قوی از بالا با حجم بالا")

        # بررسی order book
        if order_book:
            whale_ob = self.analyze_order_book_for_whales(
                order_book, candles[-1]['close']
            )
            if whale_ob['whale_pressure'] == 'buy' and whale_ob['score'] > 60:
                pump_score += 15
                reasons.append("فشار خرید نهنگی در Order Book")
            elif whale_ob['whale_pressure'] == 'sell' and whale_ob['score'] > 60:
                dump_score += 15
                reasons.append("فشار فروش نهنگی در Order Book")

        # تصمیم نهایی
        if pump_score >= dump_score and pump_score >= 30:
            return {
                "setup": "pump",
                "confidence": min(pump_score, 100),
                "reasons": reasons,
                "direction": "LONG",
            }
        elif dump_score > pump_score and dump_score >= 30:
            return {
                "setup": "dump",
                "confidence": min(dump_score, 100),
                "reasons": reasons,
                "direction": "SHORT",
            }

        return {
            "setup": "none",
            "confidence": max(pump_score, dump_score),
            "reasons": reasons,
            "direction": "NEUTRAL",
        }

    def find_whale_entry_zones(self, candles, order_book=None):
        """
        پیدا کردن ناحیه ورود نهنگ‌ها
        نهنگ‌ها معمولاً توی ناحیه‌های زیر وارد می‌شن:
        - پایین‌ترین قیمت با حجم بالا
        - بعد از sweep liquidity
        - توی Order Block
        """
        if not candles or len(candles) < 30:
            return None

        zones = []
        recent = candles[-30:]

        # پیدا کردن کندل‌های با حجم خیلی بالا (نهنگ وارد شده)
        volumes = [c['volume'] for c in recent]
        avg_vol = np.mean(volumes)
        std_vol = np.std(volumes)

        for i, c in enumerate(recent):
            if c['volume'] > avg_vol + 2 * std_vol:  # 2 sigma
                # ناحیه ورود نهنگ
                zone = {
                    "price_low": min(c['open'], c['close']),
                    "price_high": max(c['open'], c['close']),
                    "volume": c['volume'],
                    "type": "accumulation",
                    "index": i,
                }
                zones.append(zone)

        # اگه order book داریم، دیوارهای بزرگ رو هم اضافه کن
        if order_book and zones:
            ob_analysis = self.analyze_order_book_for_whales(
                order_book, candles[-1]['close']
            )
            if ob_analysis['support_wall']:
                wall = ob_analysis['support_wall']
                zones.append({
                    "price_low": wall['price'] * 0.99,
                    "price_high": wall['price'] * 1.01,
                    "volume": wall['value_usdt'] / wall['price'],
                    "type": "wall_support",
                    "wall_value": wall['value_usdt'],
                })

        return zones

    def _calculate_liquidation_zones(self, current_price, bid_walls, ask_walls):
        """محاسبه نزدیک‌ترین سطوح لیکویید"""
        zones = []

        # سطح لیکویید LONG‌ها (بالای قیمت فعلی)
        if ask_walls:
            nearest_ask = min(ask_walls, key=lambda x: x['distance_pct'])
            zones.append({
                "type": "long_liquidation",
                "price": nearest_ask['price'],
                "distance_pct": nearest_ask['distance_pct'],
                "description": f"لیکویید LONG‌ها @ {nearest_ask['price']:.2f}",
            })

        # سطح لیکویید SHORT‌ها (زیر قیمت فعلی)
        if bid_walls:
            nearest_bid = min(bid_walls, key=lambda x: x['distance_pct'])
            zones.append({
                "type": "short_liquidation",
                "price": nearest_bid['price'],
                "distance_pct": nearest_bid['distance_pct'],
                "description": f"لیکویید SHORT‌ها @ {nearest_bid['price']:.2f}",
            })

        return zones

    def _classify_wall(self, value_usdt):
        """کلاس‌بندی اندازه دیوار"""
        if value_usdt >= self.mega_wall_threshold:
            return "mega"
        elif value_usdt >= self.large_wall_threshold:
            return "large"
        return "normal"

    def _empty_result(self):
        return {
            "bid_walls": [],
            "ask_walls": [],
            "liquidation_zones": [],
            "whale_pressure": "neutral",
            "support_wall": None,
            "resistance_wall": None,
            "score": 50,
            "reasons": ["داده order book ناکافی"],
            "total_bid_value": 0,
            "total_ask_value": 0,
        }
