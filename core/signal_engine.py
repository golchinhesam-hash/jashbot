# -*- coding: utf-8 -*-
"""
موتور تولید سیگنال
ترکیب تمام تحلیل‌ها (order flow, liquidity, whale) برای تولید سیگنال نهایی
خروجی: سیگنال با entry, stop loss, take profit, risk/reward
"""

import logging
import time
from config import (
    MIN_TARGET_PROFIT,
    MIN_TARGET_PROFIT_SHITCOIN,
    MIN_RISK_REWARD,
    MAX_STOP_LOSS_PCT,
    STOP_LOSS_BUFFER,
    TP_LEVELS,
    TP_RATIOS,
    MIN_SIGNAL_SCORE,
    SHITCOIN_SYMBOLS,
    SIGNAL_TYPE,
    FUTURES_LEVERAGE_MAIN,
    FUTURES_LEVERAGE_SHITCOIN,
    MAX_FUTURES_STOP_PCT_MAIN,
    MAX_FUTURES_STOP_PCT_SHITCOIN,
    FUTURES_TP_RATIOS,
    FUTURES_TP_RATIOS_SHITCOIN,
    MIN_FUTURES_PROFIT_MAIN,
    MIN_FUTURES_PROFIT_SHITCOIN,
    MIN_FUTURES_SCORE_MAIN,
    MIN_FUTURES_SCORE_SHITCOIN,
)
from core.order_flow import OrderFlowAnalyzer
from core.liquidity import LiquidityScanner
from core.whale_scanner import WhaleScanner

logger = logging.getLogger(__name__)


class SignalEngine:
    """موتور ترکیب سیگنال‌ها و تولید سیگنال نهایی"""

    def __init__(self, market_data):
        self.market = market_data
        self.order_flow = OrderFlowAnalyzer()
        self.liquidity = LiquidityScanner()
        self.whale = WhaleScanner()
        self.signal_history = {}  # symbol -> last_signal_time

    def quick_scan(self, symbol, base=None, is_shitcoin=False):
        """
        اسکن سریع - فقط با klines 1h (1 API call)
        برای فیلتر اولیه از بین صدها ارز
        برمی‌گردونه: (symbol, base, is_shitcoin, quick_score, direction_hint)
        یا None اگه داده ناکافی باشه
        """
        try:
            candles_1h = self.market.get_candles(symbol, "1h", 100)
            if not candles_1h or len(candles_1h) < 20:
                return None

            # تحلیل سریع order flow
            of_result = self.order_flow.analyze_candle_flow(candles_1h)
            of_score = of_result.get("score", 50)
            of_trend = of_result.get("trend", "neutral")

            # تحلیل سریع liquidity
            sr = self.liquidity.find_support_resistance(candles_1h)
            current_price = candles_1h[-1]["close"]

            liq_score = 50
            direction_hint = "NEUTRAL"

            nearest_support = sr.get("nearest_support")
            nearest_resistance = sr.get("nearest_resistance")

            if nearest_support and nearest_resistance:
                support_dist = (current_price - nearest_support) / current_price * 100
                resistance_dist = (nearest_resistance - current_price) / current_price * 100

                if support_dist < 3:
                    liq_score += 15
                    direction_hint = "LONG"
                elif resistance_dist < 3:
                    liq_score -= 15
                    direction_hint = "SHORT"

            # CVD سریع
            cvd = self.whale.analyze_cvd(candles_1h)
            cvd_score = cvd.get("score", 50)

            # ناهنجاری حجم
            vol_anomalies = self.whale.scan_volume_anomalies(candles_1h)
            vol_trend = vol_anomalies.get("trend", "neutral")

            # امتیاز سریع
            quick_score = (of_score + liq_score + cvd_score) / 3

            # تنظیم direction با order flow
            if of_trend == "bullish" and direction_hint != "SHORT":
                direction_hint = "LONG"
            elif of_trend == "bearish" and direction_hint != "LONG":
                direction_hint = "SHORT"
            elif vol_trend == "buy" and direction_hint == "NEUTRAL":
                direction_hint = "LONG"
            elif vol_trend == "sell" and direction_hint == "NEUTRAL":
                direction_hint = "SHORT"

            return (symbol, base, is_shitcoin, quick_score, direction_hint)

        except Exception as e:
            logger.debug(f"خطا در quick_scan {symbol}: {e}")
            return None

    def scan_symbol(self, symbol, base=None, is_shitcoin=False):
        """
        اسکن کامل یک ارز و تولید سیگنال

        مراحل:
        1. دریافت داده چند تایم‌فریم
        2. تحلیل order flow
        3. اسکن liquidity
        4. اسکن نهنگ‌ها
        5. ترکیب و تولید سیگنال

        is_shitcoin: اگه True باشه، معیارهای متفاوتی اعمال میشه
        (حداقل سود بالاتر، استاپ عریض‌تر)
        """
        try:
            # دریافت داده‌ها
            candles_1h = self.market.get_candles(symbol, "1h", 200)
            candles_15m = self.market.get_candles(symbol, "15m", 200)
            candles_4h = self.market.get_candles(symbol, "4h", 200)

            if not candles_1h or len(candles_1h) < 20:
                logger.debug(f"داده ناکافی برای {symbol}")
                return None

            # تحلیل order flow (روی 1h)
            of_result = self.order_flow.analyze_candle_flow(candles_1h)

            # تحلیل تریدهای اخیر
            trades = self.market.get_recent_trades(symbol, 500)
            trade_flow = self.order_flow.analyze_trade_flow(trades) if trades else None

            # اسکن liquidity
            sr = self.liquidity.find_support_resistance(candles_1h)
            pools = self.liquidity.find_liquidity_pools(candles_1h)

            # اسکن order book walls
            order_book = self.market.get_order_book(symbol, 100)
            book_walls = self.liquidity.analyze_order_book_walls(order_book)

            # اسکن نهنگ‌ها
            whale_trades = self.whale.scan_whale_trades(trades) if trades else None
            vol_anomalies = self.whale.scan_volume_anomalies(candles_1h)
            cvd = self.whale.analyze_cvd(candles_1h)

            # تحلیل تایم‌فریم بالاتر (4h) برای روند کلی
            of_4h = self.order_flow.analyze_candle_flow(candles_4h) if candles_4h else None

            # ترکیب و تولید سیگنال
            signal = self._generate_signal(
                symbol=symbol,
                base=base,
                candles_1h=candles_1h,
                candles_15m=candles_15m,
                of_result=of_result,
                trade_flow=trade_flow,
                sr=sr,
                pools=pools,
                book_walls=book_walls,
                whale_trades=whale_trades,
                vol_anomalies=vol_anomalies,
                cvd=cvd,
                of_4h=of_4h,
                is_shitcoin=is_shitcoin,
            )

            return signal

        except Exception as e:
            logger.error(f"خطا در اسکن {symbol}: {e}")
            return None

    def _generate_signal(self, symbol, base, candles_1h, candles_15m,
                         of_result, trade_flow, sr, pools, book_walls,
                         whale_trades, vol_anomalies, cvd, of_4h,
                         is_shitcoin=False):
        """ترکیب تمام تحلیل‌ها و تولید سیگنال نهایی"""

        current_price = candles_1h[-1]["close"]
        reasons = []
        scores = []
        direction_votes = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}

        # === 1. Order Flow ===
        of_score = of_result.get("score", 50)
        scores.append(("Order Flow", of_score))
        of_trend = of_result.get("trend", "neutral")
        if of_trend == "bullish":
            direction_votes["LONG"] += 2
            reasons.append(f"Order Flow: فشار خریدار قوی (نسبت {of_result.get('delta_ratio', 1):.2f}:1)")
        elif of_trend == "bearish":
            direction_votes["SHORT"] += 2
            reasons.append(f"Order Flow: فشار فروشنده قوی (نسبت {1/of_result.get('delta_ratio', 1):.2f}:1)")

        for sig in of_result.get("signals", [])[:3]:
            reasons.append(f"OF: {sig}")

        # === 2. Trade Flow (tick level) ===
        if trade_flow:
            tf_trend = trade_flow.get("trend", "neutral")
            tf_ratio = trade_flow.get("ratio", 1.0)
            if tf_trend == "bullish":
                direction_votes["LONG"] += 1
                reasons.append(f"تریدهای اخیر: خرید market قوی (نسبت {tf_ratio:.2f}:1)")
            elif tf_trend == "bearish":
                direction_votes["SHORT"] += 1
                reasons.append(f"تریدهای اخیر: فروش market قوی (نسبت {1/tf_ratio:.2f}:1)")

        # === 3. Liquidity / Support-Resistance ===
        nearest_support = sr.get("nearest_support")
        nearest_resistance = sr.get("nearest_resistance")
        liq_score = 50

        # فاصله از حمایت/مقاومت
        if nearest_support and nearest_resistance:
            support_dist = (current_price - nearest_support) / current_price * 100
            resistance_dist = (nearest_resistance - current_price) / current_price * 100

            # اگه نزدیک حمایت باشه = فرصت خرید
            if support_dist < 3:
                direction_votes["LONG"] += 2
                liq_score += 15
                reasons.append(f"نزدیک حمایت ({support_dist:.1f}% فاصله)")
            # اگه نزدیک مقاومت باشه = فرصت فروش
            elif resistance_dist < 3:
                direction_votes["SHORT"] += 2
                liq_score -= 15
                reasons.append(f"نزدیک مقاومت ({resistance_dist:.1f}% فاصله)")

            # فاصله سود تا مقاومت
            if resistance_dist >= MIN_TARGET_PROFIT:
                liq_score += 10
                reasons.append(f"فاصله تا مقاومت بعدی: {resistance_dist:.1f}% (کافی برای هدف سود)")

        scores.append(("Liquidity/SR", liq_score))

        # === 4. Order Book Walls ===
        book_imbalance = book_walls.get("imbalance", 0)
        if book_imbalance > 0.3:
            direction_votes["LONG"] += 1
            reasons.append(f"دیوار خرید قوی در order book (imbalance: {book_imbalance:.2f})")
            scores.append(("Order Book", 65))
        elif book_imbalance < -0.3:
            direction_votes["SHORT"] += 1
            reasons.append(f"دیوار فروش قوی در order book (imbalance: {book_imbalance:.2f})")
            scores.append(("Order Book", 35))
        else:
            scores.append(("Order Book", 50))

        # === 5. Whale Activity ===
        whale_score = 50
        if whale_trades:
            whale_dir = whale_trades.get("direction", "neutral")
            whale_score = whale_trades.get("score", 50)
            net_flow = whale_trades.get("net_whale_flow", 0)

            if whale_dir == "buy":
                direction_votes["LONG"] += 2
                reasons.append(
                    f"نهنگ‌ها در حال خرید: {whale_trades.get('whale_buy_count', 0)} ترید بزرگ "
                    f"(خالص: {net_flow/1000:.0f}K USDT)"
                )
            elif whale_dir == "sell":
                direction_votes["SHORT"] += 2
                reasons.append(
                    f"نهنگ‌ها در حال فروش: {whale_trades.get('whale_sell_count', 0)} ترید بزرگ "
                    f"(خالص: {net_flow/1000:.0f}K USDT)"
                )

        # حجم ناهنجاری
        vol_trend = vol_anomalies.get("trend", "neutral")
        if vol_trend == "buy":
            direction_votes["LONG"] += 1
            reasons.append(f"ناهنجاری حجم صعودی ({vol_anomalies.get('anomaly_count', 0)} مورد)")
        elif vol_trend == "sell":
            direction_votes["SHORT"] += 1
            reasons.append(f"ناهنجاری حجم نزولی ({vol_anomalies.get('anomaly_count', 0)} مورد)")

        scores.append(("Whale", whale_score))

        # === 6. CVD ===
        cvd_score = cvd.get("score", 50)
        cvd_trend = cvd.get("cvd_trend", "flat")
        cvd_div = cvd.get("cvd_divergence", "none")

        if cvd_trend == "rising":
            direction_votes["LONG"] += 1
            reasons.append("CVD صعودی - فشار خرید تجمعی در حال افزایش")
        elif cvd_trend == "falling":
            direction_votes["SHORT"] += 1
            reasons.append("CVD نزولی - فشار فروش تجمعی در حال افزایش")

        if cvd_div == "bullish":
            direction_votes["LONG"] += 1
            reasons.append("واگرایی صعودی CVD - فرصت خرید احتمالی")
        elif cvd_div == "bearish":
            direction_votes["SHORT"] += 1
            reasons.append("واگرایی نزولی CVD - هشدار")

        scores.append(("CVD", cvd_score))

        # === 7. تایم‌فریم بالاتر (4h) ===
        if of_4h:
            h4_trend = of_4h.get("trend", "neutral")
            h4_score = of_4h.get("score", 50)
            if h4_trend == "bullish":
                direction_votes["LONG"] += 2
                reasons.append("روند 4H صعودی - تایید جهت")
            elif h4_trend == "bearish":
                direction_votes["SHORT"] += 2
                reasons.append("روند 4H نزولی - تایید جهت")
            scores.append(("4H Trend", h4_score))

        # === تصمیم نهایی ===
        total_score = sum(s[1] for s in scores) / len(scores) if scores else 50

        # تعیین جهت
        # برای شت‌کوین، آستانه رأی کمتر چون نوسان بالاتره
        vote_threshold = 3 if is_shitcoin else 4

        if direction_votes["LONG"] >= vote_threshold and direction_votes["LONG"] > direction_votes["SHORT"]:
            direction = "LONG"
        elif direction_votes["SHORT"] >= vote_threshold and direction_votes["SHORT"] > direction_votes["LONG"]:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        # برای فیوچر، حداقل امتیاز سخت‌گیرانه‌تر (جلوگیری از استاپ/لیکویید)
        if SIGNAL_TYPE == "futures":
            min_score = MIN_FUTURES_SCORE_SHITCOIN if is_shitcoin else MIN_FUTURES_SCORE_MAIN
        else:
            min_score = 60 if is_shitcoin else MIN_SIGNAL_SCORE

        # اگه امتیاز کافی نبود یا جهت خنثی بود
        if direction == "NEUTRAL" or total_score < min_score:
            return {
                "symbol": symbol,
                "base": base or symbol,
                "direction": "NEUTRAL",
                "score": total_score,
                "reasons": reasons,
                "is_shitcoin": is_shitcoin,
                "analysis": {
                    "order_flow": of_result,
                    "liquidity": sr,
                    "whale": whale_trades,
                    "cvd": cvd,
                    "scores": scores,
                },
            }

        # === محاسبه Entry, SL, TP, Leverage ===
        entry, stop_loss, take_profits, rr, expected_profit, leverage = self._calculate_levels(
            current_price, direction, sr, pools, book_walls, is_shitcoin
        )

        # معیارهای متفاوت برای فیوچر vs spot، و شت‌کوین vs اصلی
        if SIGNAL_TYPE == "futures":
            min_rr = 2.0  # حداقل R:R برای فیوچر
            min_profit = MIN_FUTURES_PROFIT_SHITCOIN if is_shitcoin else MIN_FUTURES_PROFIT_MAIN
        else:
            min_rr = 1.5 if is_shitcoin else MIN_RISK_REWARD
            min_profit = MIN_TARGET_PROFIT_SHITCOIN if is_shitcoin else MIN_TARGET_PROFIT

        # بررسی معیارها
        if rr < min_rr:
            reasons.append(f"Risk/Reward پایین ({rr:.2f}) - سیگنال رد شد")
            return {
                "symbol": symbol,
                "base": base or symbol,
                "direction": "NEUTRAL",
                "score": total_score,
                "reasons": reasons,
                "is_shitcoin": is_shitcoin,
                "analysis": {"scores": scores},
            }

        if expected_profit < min_profit:
            reasons.append(f"سود مورد انتظار کم ({expected_profit:.1f}%) - سیگنال رد شد")
            return {
                "symbol": symbol,
                "base": base or symbol,
                "direction": "NEUTRAL",
                "score": total_score,
                "reasons": reasons,
                "analysis": {"scores": scores},
            }

        return {
            "symbol": symbol,
            "base": base or symbol,
            "direction": direction,
            "score": total_score,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profits": take_profits,
            "risk_reward": rr,
            "expected_profit_pct": expected_profit,
            "current_price": current_price,
            "leverage": leverage,
            "reasons": reasons,
            "timestamp": time.time(),
            "analysis": {
                "order_flow": {
                    "trend": of_result.get("trend"),
                    "delta_ratio": of_result.get("delta_ratio"),
                    "score": of_result.get("score"),
                },
                "liquidity": {
                    "nearest_support": nearest_support,
                    "nearest_resistance": nearest_resistance,
                },
                "whale": {
                    "direction": whale_trades.get("direction") if whale_trades else None,
                    "net_flow": whale_trades.get("net_whale_flow") if whale_trades else None,
                    "score": whale_trades.get("score") if whale_trades else None,
                },
                "cvd": {
                    "trend": cvd.get("cvd_trend"),
                    "divergence": cvd.get("cvd_divergence"),
                },
                "scores": scores,
            },
        }

    def _calculate_levels(self, current_price, direction, sr, pools, book_walls, is_shitcoin=False):
        """محاسبه دقیق Entry, Stop Loss, Take Profit برای سیگنال فیوچر"""

        # برای فیوچر: استاپ‌های تighter برای جلوگیری از لیکویید شدن
        if SIGNAL_TYPE == "futures":
            max_sl_pct = MAX_FUTURES_STOP_PCT_SHITCOIN if is_shitcoin else MAX_FUTURES_STOP_PCT_MAIN
            sl_buffer = 1.0  # بافر کمتر برای فیوچر
        else:
            max_sl_pct = MAX_STOP_LOSS_PCT * 2 if is_shitcoin else MAX_STOP_LOSS_PCT
            sl_buffer = STOP_LOSS_BUFFER * 2 if is_shitcoin else STOP_LOSS_BUFFER

        nearest_support = sr.get("nearest_support")
        nearest_resistance = sr.get("nearest_resistance")

        if direction == "LONG":
            # ورود: قیمت فعلی
            entry = current_price

            # استاپ: زیر حمایت نزدیک + بافر
            if nearest_support and nearest_support < current_price:
                support_dist_pct = (current_price - nearest_support) / current_price * 100
                if support_dist_pct <= max_sl_pct:
                    stop_loss = nearest_support * (1 - sl_buffer / 100)
                else:
                    stop_loss = current_price * (1 - max_sl_pct / 100)
            else:
                stop_loss = current_price * (1 - max_sl_pct / 100)

            # اگه دیوار خرید قوی در order book هست
            bid_walls = book_walls.get("bid_walls", [])
            if bid_walls:
                strongest_wall = bid_walls[0]
                if strongest_wall["price"] < current_price and strongest_wall["price"] > stop_loss:
                    stop_loss = min(stop_loss, strongest_wall["price"] * 0.995)

            # محاسبه ریسک
            risk = entry - stop_loss

            # Take Profit - برای فیوچر اهداف بالاتر
            if SIGNAL_TYPE == "futures":
                tp_ratios = FUTURES_TP_RATIOS_SHITCOIN if is_shitcoin else FUTURES_TP_RATIOS
            else:
                tp_ratios = [2.0, 4.0, 7.0] if is_shitcoin else TP_RATIOS
            take_profits = []
            for ratio in tp_ratios[:TP_LEVELS]:
                tp = entry + (risk * ratio)
                take_profits.append(round(tp, 8))

            expected_profit = (take_profits[-1] - entry) / entry * 100

        else:  # SHORT
            entry = current_price

            # استاپ: بالای مقاومت نزدیک + بافر
            if nearest_resistance and nearest_resistance > current_price:
                resistance_dist_pct = (nearest_resistance - current_price) / current_price * 100
                if resistance_dist_pct <= max_sl_pct:
                    stop_loss = nearest_resistance * (1 + sl_buffer / 100)
                else:
                    stop_loss = current_price * (1 + max_sl_pct / 100)
            else:
                stop_loss = current_price * (1 + max_sl_pct / 100)

            ask_walls = book_walls.get("ask_walls", [])
            if ask_walls:
                strongest_wall = ask_walls[0]
                if strongest_wall["price"] > current_price and strongest_wall["price"] < stop_loss:
                    stop_loss = max(stop_loss, strongest_wall["price"] * 1.005)

            risk = stop_loss - entry

            if SIGNAL_TYPE == "futures":
                tp_ratios = FUTURES_TP_RATIOS_SHITCOIN if is_shitcoin else FUTURES_TP_RATIOS
            else:
                tp_ratios = [2.0, 4.0, 7.0] if is_shitcoin else TP_RATIOS
            take_profits = []
            for ratio in tp_ratios[:TP_LEVELS]:
                tp = entry - (risk * ratio)
                take_profits.append(round(tp, 8))

            expected_profit = (entry - take_profits[-1]) / entry * 100

        risk_reward = tp_ratios[-1] if 'tp_ratios' in dir() else TP_RATIOS[-1]

        # محاسبه لیکویید قیمت برای فیوچر
        leverage = FUTURES_LEVERAGE_SHITCOIN if is_shitcoin else FUTURES_LEVERAGE_MAIN

        return round(entry, 8), round(stop_loss, 8), take_profits, risk_reward, expected_profit, leverage

    def should_send_signal(self, symbol):
        """بررسی cooldown - جلوگیری از ارسال سیگنال تکراری"""
        now = time.time()
        last = self.signal_history.get(symbol, 0)
        from config import SIGNAL_COOLDOWN
        if now - last < SIGNAL_COOLDOWN:
            return False
        return True

    def mark_signal_sent(self, symbol):
        """ثبت زمان ارسال سیگنال"""
        self.signal_history[symbol] = time.time()

    def format_signal_message(self, signal):
        """فرمت‌بندی سیگنال فیوچر برای ارسال به تلگرام"""
        if signal.get("direction") == "NEUTRAL":
            return None

        symbol = signal.get("symbol", "")
        base = signal.get("base", symbol)
        direction = signal.get("direction", "")
        score = signal.get("score", 0)
        entry = signal.get("entry", 0)
        stop_loss = signal.get("stop_loss", 0)
        take_profits = signal.get("take_profits", [])
        rr = signal.get("risk_reward", 0)
        expected_profit = signal.get("expected_profit_pct", 0)
        reasons = signal.get("reasons", [])
        is_shitcoin = signal.get("is_shitcoin", False)
        leverage = signal.get("leverage", 10)
        current_price = signal.get("current_price", entry)

        # تشخیص تعداد اعشار مناسب
        if entry < 1:
            fmt = lambda x: f"{x:.6f}"
        elif entry < 100:
            fmt = lambda x: f"{x:.4f}"
        else:
            fmt = lambda x: f"{x:.2f}"

        emoji = "🟢" if direction == "LONG" else "🔴"
        tag = " 🐕 شت‌کوین" if is_shitcoin else ""

        # درصد فاصله استاپ
        sl_pct = abs(entry - stop_loss) / entry * 100

        # قیمت لیکویید تقریبی (با اهرم)
        if direction == "LONG":
            liq_price = entry * (1 - 1.0 / leverage * 0.95)  # 95% از حاشیه لیکویید
        else:
            liq_price = entry * (1 + 1.0 / leverage * 0.95)

        msg = f"""
{emoji} سیگنال فیوچر {direction} - {base}{tag} {emoji}

📊 امتیاز: {score:.0f}/100
⚡ اهرم پیشنهادی: {leverage}x
💰 ورود: {fmt(entry)}
🛑 استاپ لاس: {fmt(stop_loss)} ({sl_pct:.1f}%)
💀 قیمت لیکویید: {fmt(liq_price)}"""

        for i, tp in enumerate(take_profits, 1):
            tp_pct = abs(tp - entry) / entry * 100
            msg += f"\n🎯 هدف {i}: {fmt(tp)} (+{tp_pct:.1f}%)"

        msg += f"""

📐 Risk/Reward: {rr:.1f}:1
📈 سود مورد انتظار: {expected_profit:.1f}%
💰 سود با اهرم {leverage}x: ~{expected_profit * leverage:.0f}%

📋 دلایل سیگنال:
"""
        for r in reasons:
            msg += f"  • {r}\n"

        msg += f"\n⏰ زمان: {time.strftime('%Y-%m-%d %H:%M', time.localtime(signal.get('timestamp', time.time())))}"
        msg += "\n\n⚠️ **هشدار:** این سیگنال توسط ربات تولید شده و نظر سرمایه‌گذاری نیست. مسئولیت معامله با شماست."
        msg += "\n🔧 سیگنال فیوچر - حتماً با مدیریت ریسک مناسب وارد شوید."

        return msg
