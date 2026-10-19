# -*- coding: utf-8 -*-
"""
اسکن نواحی نقدینگی و حمایت/مقاومت
شناسایی: equal highs/lows, liquidity pools, order book walls
"""

import logging
import numpy as np
from collections import defaultdict
from config import SR_ZONE_THRESHOLD, LIQUIDITY_LOOKBACK_HOURS

logger = logging.getLogger(__name__)


class LiquidityScanner:
    """اسکن نواحی نقدینگی و حمایت/مقاومت"""

    def __init__(self):
        self.zone_threshold = SR_ZONE_THRESHOLD  # درصد
        self.lookback_hours = LIQUIDITY_LOOKBACK_HOURS

    def find_support_resistance(self, candles):
        """
        شناسایی نواحی حمایت و مقاومت از روی swing highs و swing lows

        برمی‌گردونه:
        {
            "resistances": [{"price": float, "strength": int, "touches": int}, ...],
            "supports": [{"price": float, "strength": int, "touches": int}, ...],
            "nearest_resistance": float,
            "nearest_support": float,
            "current_price": float,
        }
        """
        if len(candles) < 20:
            return self._empty_sr()

        recent = candles[-self.lookback_hours * 4:] if len(candles) > self.lookback_hours * 4 else candles
        current_price = candles[-1]["close"]

        # شناسایی swing highs و lows
        swing_highs = []
        swing_lows = []
        window = 5  # پنجره برای swing detection

        for i in range(window, len(recent) - window):
            # Swing high: بالاترین high در پنجره
            is_high = all(
                recent[i]["high"] >= recent[i+j]["high"]
                for j in range(-window, window+1) if j != 0
            )
            if is_high:
                swing_highs.append({"price": recent[i]["high"], "index": i, "time": recent[i]["time"]})

            # Swing low: پایین‌ترین low در پنجره
            is_low = all(
                recent[i]["low"] <= recent[i+j]["low"]
                for j in range(-window, window+1) if j != 0
            )
            if is_low:
                swing_lows.append({"price": recent[i]["low"], "index": i, "time": recent[i]["time"]})

        # تجمیع سطوح نزدیک به هم
        resistances = self._cluster_levels(swing_highs, current_price, above=True)
        supports = self._cluster_levels(swing_lows, current_price, above=False)

        # مرتب‌سازی
        resistances.sort(key=lambda x: x["price"])
        supports.sort(key=lambda x: x["price"], reverse=True)

        nearest_resistance = None
        for r in resistances:
            if r["price"] > current_price:
                nearest_resistance = r["price"]
                break

        nearest_support = None
        for s in supports:
            if s["price"] < current_price:
                nearest_support = s["price"]
                break

        return {
            "resistances": resistances,
            "supports": supports,
            "nearest_resistance": nearest_resistance,
            "nearest_support": nearest_support,
            "current_price": current_price,
        }

    def find_liquidity_pools(self, candles):
        """
        شناسایی استخرهای نقدینگی (liquidity pools)
        نواحی که قیمت چندبار به اونجا رسیده و برگشته

        برمی‌گردونه:
        {
            "pools": [{"price": float, "type": "buy" or "sell", "strength": int}, ...],
            "equal_highs": list,  # برابری سقف‌ها - نقدینگی فروش
            "equal_lows": list,   # برابری کف‌ها - نقدینگی خرید
        }
        """
        if len(candles) < 20:
            return {"pools": [], "equal_highs": [], "equal_lows": []}

        recent = candles[-100:]
        tolerance = self.zone_threshold / 100

        # محاسبه میانگین قیمت برای تعیین تلورانس
        avg_price = np.mean([c["close"] for c in recent])
        price_tolerance = avg_price * tolerance

        # پیدا کردن equal highs (سقف‌های برابر)
        highs = [c["high"] for c in recent]
        equal_highs = self._find_equal_levels(highs, price_tolerance)

        # پیدا کردن equal lows (کف‌های برابر)
        lows = [c["low"] for c in recent]
        equal_lows = self._find_equal_levels(lows, price_tolerance)

        pools = []
        # equal highs = ناحیه نقدینگی فروش (stop loss buy side)
        for eh in equal_highs:
            pools.append({
                "price": eh["price"],
                "type": "sell",
                "strength": eh["count"],
            })

        # equal lows = ناحیه نقدینگی خرید (stop loss sell side)
        for el in equal_lows:
            pools.append({
                "price": el["price"],
                "type": "buy",
                "strength": el["count"],
            })

        return {
            "pools": pools,
            "equal_highs": equal_highs,
            "equal_lows": equal_lows,
        }

    def analyze_order_book_walls(self, order_book):
        """
        تحلیل دیوارهای order book
        شناسایی سفارشات بزرگ در bids و asks

        برمی‌گردونه:
        {
            "bid_walls": [{"price": float, "size": float}, ...],
            "ask_walls": [{"price": float, "size": float}, ...],
            "bid_wall_total": float,
            "ask_wall_total": float,
            "imbalance": float,  # > 0 = خرید قوی‌تر
        }
        """
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        if not bids or not asks:
            return self._empty_book_result()

        # محاسبه میانگین حجم برای تشخیص دیوارها
        bid_sizes = [b[1] for b in bids]
        ask_sizes = [a[1] for a in asks]
        avg_bid = np.mean(bid_sizes) if bid_sizes else 0
        avg_ask = np.mean(ask_sizes) if ask_sizes else 0

        bid_walls = []
        ask_walls = []

        wall_threshold = 3  # 3 برابر میانگین

        for b in bids:
            if b[1] > avg_bid * wall_threshold:
                bid_walls.append({"price": b[0], "size": b[1]})

        for a in asks:
            if a[1] > avg_ask * wall_threshold:
                ask_walls.append({"price": a[0], "size": a[1]})

        # مرتب بر اساس حجم
        bid_walls.sort(key=lambda x: x["size"], reverse=True)
        ask_walls.sort(key=lambda x: x["size"], reverse=True)

        bid_wall_total = sum(w["size"] * w["price"] for w in bid_walls)
        ask_wall_total = sum(w["size"] * w["price"] for w in ask_walls)

        imbalance = (bid_wall_total - ask_wall_total) / (bid_wall_total + ask_wall_total) if (bid_wall_total + ask_wall_total) > 0 else 0

        return {
            "bid_walls": bid_walls[:5],
            "ask_walls": ask_walls[:5],
            "bid_wall_total": bid_wall_total,
            "ask_wall_total": ask_wall_total,
            "imbalance": imbalance,
        }

    def _find_equal_levels(self, prices, tolerance):
        """پیدا کردن سطوح برابر (equal highs/lows)"""
        if len(prices) < 2:
            return []

        # گروه‌بندی سطوح نزدیک به هم
        groups = []
        used = [False] * len(prices)

        for i in range(len(prices)):
            if used[i]:
                continue
            group = {"prices": [prices[i]], "indices": [i]}
            used[i] = True
            for j in range(i + 1, len(prices)):
                if used[j]:
                    continue
                if abs(prices[j] - prices[i]) <= tolerance:
                    group["prices"].append(prices[j])
                    group["indices"].append(j)
                    used[j] = True
            if len(group["prices"]) >= 2:
                avg = np.mean(group["prices"])
                groups.append({
                    "price": avg,
                    "count": len(group["prices"]),
                    "strength": len(group["prices"]),
                })

        return groups

    def _cluster_levels(self, swings, current_price, above=True):
        """تجمیع سطوح نزدیک به هم"""
        if not swings:
            return []

        tolerance = current_price * (self.zone_threshold / 100)
        clusters = []

        for s in swings:
            added = False
            for c in clusters:
                if abs(s["price"] - c["price"]) <= tolerance:
                    c["price"] = (c["price"] * c["touches"] + s["price"]) / (c["touches"] + 1)
                    c["touches"] += 1
                    c["strength"] = c["touches"]
                    added = True
                    break
            if not added:
                clusters.append({
                    "price": s["price"],
                    "touches": 1,
                    "strength": 1,
                })

        # مرتب بر اساس قدرت
        clusters.sort(key=lambda x: x["strength"], reverse=True)
        return clusters

    def _empty_sr(self):
        return {
            "resistances": [],
            "supports": [],
            "nearest_resistance": None,
            "nearest_support": None,
            "current_price": 0,
        }

    def _empty_book_result(self):
        return {
            "bid_walls": [],
            "ask_walls": [],
            "bid_wall_total": 0,
            "ask_wall_total": 0,
            "imbalance": 0,
        }
