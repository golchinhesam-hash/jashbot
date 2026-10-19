# -*- coding: utf-8 -*-
"""
اسکن فعالیت نهنگ‌ها
شناسایی جابجایی‌های بزرگ از روی:
1. تریدهای بزرگ در recent trades
2. کندل‌های با حجم غیرعادی
3. تغییرات حجم ناگهانی
"""

import logging
import numpy as np
from collections import deque
from config import WHALE_TX_THRESHOLD, WHALE_TX_LIMIT, WHALE_SIGNAL_THRESHOLD

logger = logging.getLogger(__name__)


class WhaleScanner:
    """اسکن فعالیت نهنگ‌ها و جابجایی‌های بزرگ"""

    def __init__(self):
        self.tx_threshold = WHALE_TX_THRESHOLD  # 100K (پایین آورده شد)
        self.tx_limit = WHALE_TX_LIMIT
        self.signal_threshold = 1  # حداقل 1 ترید نهنگ (پایین آورده شد از 3)

    def scan_whale_trades(self, trades):
        """
        اسکن تریدهای اخیر برای شناسایی فعالیت نهنگ‌ها

        برمی‌گردونه:
        {
            "whale_buy_count": int,
            "whale_sell_count": int,
            "whale_buy_volume": float,   # به USDT
            "whale_sell_volume": float,
            "net_whale_flow": float,     # مثبت = ورود نهنگ‌ها
            "direction": str,            # "buy" / "sell" / "neutral"
            "whale_trades": list,
            "score": int,               # 0-100
        }
        """
        if not trades:
            return self._empty_whale_result()

        whale_buy_count = 0
        whale_sell_count = 0
        whale_buy_volume = 0
        whale_sell_volume = 0
        whale_trades = []

        # محاسبه مجموع حجم معاملات برای آستانه پویا
        all_notional = [t["price"] * t["qty"] for t in trades]
        total_notional = sum(all_notional)
        avg_trade = total_notional / len(trades) if trades else 0

        # آستانه پویا: ماکزیمم آستانه ثابت و 5x میانگین
        dynamic_threshold = max(self.tx_threshold, avg_trade * 5)

        for t in trades:
            notional = t["price"] * t["qty"]
            if notional < dynamic_threshold:
                continue

            whale_trades.append({
                "price": t["price"],
                "value": notional,
                "isBuyerMaker": t["isBuyerMaker"],
                "direction": "sell" if t["isBuyerMaker"] else "buy",
            })

            if t["isBuyerMaker"]:
                whale_sell_count += 1
                whale_sell_volume += notional
            else:
                whale_buy_count += 1
                whale_buy_volume += notional

        net_flow = whale_buy_volume - whale_sell_volume

        # تشخیص جهت - با آستانه پایین‌تر
        if whale_buy_count >= self.signal_threshold and whale_buy_count > whale_sell_count:
            direction = "buy"
        elif whale_sell_count >= self.signal_threshold and whale_sell_count > whale_buy_count:
            direction = "sell"
        else:
            direction = "neutral"

        score = self._calculate_score(
            whale_buy_count, whale_sell_count,
            whale_buy_volume, whale_sell_volume
        )

        return {
            "whale_buy_count": whale_buy_count,
            "whale_sell_count": whale_sell_count,
            "whale_buy_volume": whale_buy_volume,
            "whale_sell_volume": whale_sell_volume,
            "net_whale_flow": net_flow,
            "direction": direction,
            "whale_trades": whale_trades[:10],
            "score": score,
        }

    def scan_volume_anomalies(self, candles):
        """
        اسکن ناهنجاری‌های حجم در کندل‌ها
        شناسایی کندل‌هایی با حجم بسیار غیرعادی که احتمالا نهنگ‌ها فعال بودن

        برمی‌گردونه:
        {
            "anomalies": [{"time": int, "volume": float, "price": float, "bullish": bool}, ...],
            "recent_volume_avg": float,
            "anomaly_count": int,
            "trend": str,
        }
        """
        if len(candles) < 20:
            return {"anomalies": [], "recent_volume_avg": 0, "anomaly_count": 0, "trend": "neutral"}

        recent = candles[-50:]
        volumes = [c["volume"] for c in recent]

        # محاسبه میانگین و انحراف معیار
        avg_vol = np.mean(volumes)
        std_vol = np.std(volumes)

        if std_vol == 0:
            return {
                "anomalies": [],
                "recent_volume_avg": avg_vol,
                "anomaly_count": 0,
                "trend": "neutral",
            }

        # آستانه: میانگین + 2 انحراف معیار
        threshold = avg_vol + 2 * std_vol

        anomalies = []
        for c in recent:
            if c["volume"] > threshold:
                anomalies.append({
                    "time": c["time"],
                    "volume": c["volume"],
                    "price": c["close"],
                    "bullish": c["close"] >= c["open"],
                    "taker_buy_pct": c.get("takerBuyVolume", 0) / c["volume"] if c["volume"] > 0 else 0.5,
                })

        # تحلیل روند ناهنجاری‌ها
        if anomalies:
            recent_anomalies = anomalies[-5:]
            bull_count = sum(1 for a in recent_anomalies if a["bullish"])
            bear_count = len(recent_anomalies) - bull_count

            if bull_count > bear_count:
                trend = "buy"
            elif bear_count > bull_count:
                trend = "sell"
            else:
                trend = "neutral"
        else:
            trend = "neutral"

        return {
            "anomalies": anomalies,
            "recent_volume_avg": avg_vol,
            "anomaly_count": len(anomalies),
            "trend": trend,
        }

    def analyze_cvd(self, candles):
        """
        تحلیل Cumulative Volume Delta
        جمع تجمعی دلتا - نشون دهنده فشار خالص خرید/فروش در طول زمان

        برمی‌گردونه:
        {
            "cvd_current": float,
            "cvd_trend": str,       # "rising" / "falling" / "flat"
            "cvd_divergence": str,  # "bullish" / "bearish" / "none"
            "score": int,
        }
        """
        if len(candles) < 10:
            return {"cvd_current": 0, "cvd_trend": "flat", "cvd_divergence": "none", "score": 50}

        recent = candles[-30:]
        deltas = []
        prices = []

        for c in recent:
            vol = c["volume"]
            taker_buy = c.get("takerBuyVolume", vol * 0.5)
            if vol > 0:
                delta = taker_buy - (vol - taker_buy)
                deltas.append(delta)
                prices.append(c["close"])

        if not deltas:
            return {"cvd_current": 0, "cvd_trend": "flat", "cvd_divergence": "none", "score": 50}

        # CVD تجمعی
        cvd_values = np.cumsum(deltas)
        cvd_current = cvd_values[-1] if len(cvd_values) > 0 else 0

        # روند CVD - مقایسه نیمه اول و دوم
        half = len(cvd_values) // 2
        if half > 0:
            first_half = cvd_values[:half]
            second_half = cvd_values[half:]

            avg_first = np.mean(first_half) if len(first_half) > 0 else 0
            avg_second = np.mean(second_half) if len(second_half) > 0 else 0

            # آستانه کوچک برای جلوگیری از flat false
            diff_pct = (avg_second - avg_first) / (abs(avg_first) + 1e-9)
            if diff_pct > 0.02:
                cvd_trend = "rising"
            elif diff_pct < -0.02:
                cvd_trend = "falling"
            else:
                cvd_trend = "flat"
        else:
            cvd_trend = "flat"

        # بررسی واگرایی
        if len(prices) >= 2:
            price_trend = "rising" if prices[-1] > prices[0] else "falling"
            cvd_direction = "rising" if cvd_current > 0 else "falling"

            divergence = "none"
            if price_trend == "rising" and cvd_direction == "falling":
                divergence = "bearish"
            elif price_trend == "falling" and cvd_direction == "rising":
                divergence = "bullish"
        else:
            divergence = "none"

        score = 50
        if cvd_trend == "rising":
            score += 15
        elif cvd_trend == "falling":
            score -= 15

        if divergence == "bullish":
            score += 10
        elif divergence == "bearish":
            score -= 10

        return {
            "cvd_current": cvd_current,
            "cvd_trend": cvd_trend,
            "cvd_divergence": divergence,
            "score": max(0, min(100, score)),
        }

    def _calculate_score(self, buy_count, sell_count, buy_vol, sell_vol):
        """محاسبه امتیاز 0-100"""
        score = 50
        total_vol = buy_vol + sell_vol

        if total_vol > 0:
            buy_pct = buy_vol / total_vol
            # 0.5 = خنثی، >0.5 = خرید، <0.5 = فروش
            score += int((buy_pct - 0.5) * 60)

        # امتیاز تعداد
        if buy_count > sell_count:
            score += min(10, buy_count - sell_count)
        else:
            score -= min(10, sell_count - buy_count)

        return max(0, min(100, score))

    def _empty_whale_result(self):
        return {
            "whale_buy_count": 0,
            "whale_sell_count": 0,
            "whale_buy_volume": 0,
            "whale_sell_volume": 0,
            "net_whale_flow": 0,
            "direction": "neutral",
            "whale_trades": [],
            "score": 50,
        }
