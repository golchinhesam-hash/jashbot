# -*- coding: utf-8 -*-
"""
Funding Rate + Open Interest Analyzer
تحلیل نرخ فاندینگ و حجم باز برای تشخیص sentiment بازار

نرخ فاندینگ بالای مثبت = لانگ‌ها بیش از حد شلوغن = احتمال dump
نرخ فاندینگ منفی زیاد = شورت‌ها بیش از حد شلوغن = احتمال pump
"""

import logging
import requests

logger = logging.getLogger(__name__)


class FundingOIAnalyzer:
    """
    تحلیل Funding Rate و Open Interest
    برای فیلتر کردن سیگنال‌هایی که برخلاف sentiment هستن
    """

    def __init__(self):
        self.base_url = "https://fapi.binance.com"  # Futures API
        self.data_url = "https://data-api.binance.vision"

    def get_funding_rate(self, symbol):
        """
        گرفتن آخرین نرخ فاندینگ
        """
        try:
            url = f"{self.base_url}/fapi/v1/premiumIndex"
            resp = requests.get(url, params={"symbol": symbol}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "funding_rate": float(data.get("lastFundingRate", 0)),
                    "mark_price": float(data.get("markPrice", 0)),
                    "index_price": float(data.get("indexPrice", 0)),
                }
        except Exception as e:
            logger.error(f"Funding rate error for {symbol}: {e}")
        return None

    def get_open_interest(self, symbol):
        """
        گرفتن Open Interest
        """
        try:
            url = f"{self.base_url}/fapi/v1/openInterest"
            resp = requests.get(url, params={"symbol": symbol}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "open_interest": float(data.get("openInterest", 0)),
                }
        except Exception as e:
            logger.error(f"Open interest error for {symbol}: {e}")
        return None

    def get_funding_history(self, symbol, limit=3):
        """
        گرفتن تاریخچه نرخ فاندینگ (آخرین 3 دوره)
        """
        try:
            url = f"{self.base_url}/fapi/v1/fundingRate"
            resp = requests.get(url, params={"symbol": symbol, "limit": limit}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                rates = [float(d["fundingRate"]) for d in data]
                return {
                    "rates": rates,
                    "avg": sum(rates) / len(rates) if rates else 0,
                    "trend": "increasing" if rates and rates[-1] > rates[0] else "decreasing",
                }
        except Exception as e:
            logger.error(f"Funding history error for {symbol}: {e}")
        return None

    def analyze(self, symbol):
        """
        تحلیل کامل Funding + OI
        """
        funding = self.get_funding_rate(symbol)
        oi = self.get_open_interest(symbol)
        history = self.get_funding_history(symbol)

        if not funding:
            return {"status": "no_data", "score": 50, "signals": [], "direction_filter": None}

        rate = funding["funding_rate"]
        signals = []
        score_adjustment = 0
        direction_filter = None

        # Funding Rate Analysis
        # Typical range: -0.1% to +0.1% per 8 hours
        if rate > 0.001:  # > 0.1%
            signals.append(f"🔴 Funding Rate بالا: {rate*100:.3f}% (لانگ‌ها شلوغن)")
            score_adjustment -= 15
            direction_filter = "SHORT"  # Crowded longs = short opportunity
        elif rate > 0.0005:  # > 0.05%
            signals.append(f"🟠 Funding Rate مثبت: {rate*100:.3f}%")
            score_adjustment -= 8
        elif rate < -0.001:  # < -0.1%
            signals.append(f"🟢 Funding Rate منفی زیاد: {rate*100:.3f}% (شورت‌ها شلوغن)")
            score_adjustment += 15
            direction_filter = "LONG"  # Crowded shorts = long opportunity
        elif rate < -0.0005:  # < -0.05%
            signals.append(f"🔵 Funding Rate منفی: {rate*100:.3f}%")
            score_adjustment += 8
        else:
            signals.append(f"⚪ Funding Rate متعادل: {rate*100:.3f}%")

        # Funding Trend
        if history:
            avg_rate = history["avg"]
            trend = history["trend"]
            if trend == "increasing" and avg_rate > 0.0003:
                signals.append("📈 Funding Rate داره بالا میره - لانگ‌ها دارن زیاد میشن")
                score_adjustment -= 5
            elif trend == "decreasing" and avg_rate < -0.0003:
                signals.append("📉 Funding Rate داره پایین میاد - شورت‌ها دارن زیاد میشن")
                score_adjustment += 5

        # Open Interest (if available)
        if oi:
            oi_value = oi["open_interest"]
            signals.append(f"📊 Open Interest: {oi_value:,.0f}")

        return {
            "status": "active",
            "funding_rate": rate,
            "mark_price": funding.get("mark_price"),
            "open_interest": oi.get("open_interest") if oi else None,
            "funding_history": history,
            "signals": signals,
            "score_adjustment": score_adjustment,
            "direction_filter": direction_filter,
            "sentiment_score": 50 + score_adjustment,
        }
