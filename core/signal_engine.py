# -*- coding: utf-8 -*-
"""
موتور تولید سیگنال
ترکیب تمام تحلیل‌ها (order flow, liquidity, whale) برای تولید سیگنال نهایی
خروجی: سیگنال با entry, stop loss, take profit, risk/reward
"""

import logging
import time
from datetime import datetime, timedelta
from config import (
    MAX_POSITION_DURATION_HOURS,
    POSITION_EXPIRY_WARNING_MINUTES,
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
from core.whale_hunter import WhaleHunter
from core.pre_movement_detector import PreMovementDetector
from core.zone_hunter import ZoneHunter
from core.order_flow_matrix import OrderFlowMatrix
from core.market_context import MarketContextAnalyzer
from core.funding_oi import FundingOIAnalyzer

logger = logging.getLogger(__name__)

import jdatetime

# ===================== توابع کمکی زمان =====================

def get_tehran_time(timestamp=None):
    """تبدیل timestamp به زمان تهران (UTC+3:30)"""
    if timestamp is None:
        # همیشه UTC رو بگیر و 3:30 اضافه کن (حتی روی سرورهای مختلف)
        utc_now = datetime.utcnow()
        tehran_time = utc_now + timedelta(hours=3, minutes=30)
    else:
        # از timestamp: ابتدا UTC، بعد +3:30
        utc_dt = datetime.utcfromtimestamp(timestamp)
        tehran_time = utc_dt + timedelta(hours=3, minutes=30)
    return tehran_time


# ===================== توابع ICT (Michael Huddleston) =====================

def is_ict_killzone():
    """چک کردن زمان‌های کلیدی بازار (برای کریپتو 24/7)
    
    Asian Session: 03:30 - 07:30 Tehran (01:00 - 05:00 GMT) - Tokyo open
    London Session: 10:30 - 13:30 Tehran (08:00 - 11:00 GMT)
    NY Session: 16:00 - 19:00 Tehran (13:30 - 16:30 GMT)
    NY Close: 21:00 - 22:00 Tehran (18:30 - 19:30 GMT)
    
    NOTE: For crypto 24/7 markets, these are high volatility periods,
    not hard filters. Signals can fire at any time.
    """
    dt = get_tehran_time()
    hour = dt.hour
    minute = dt.minute
    time_val = hour + minute / 60.0
    
    # Asian Session (Tokyo): 03:30 - 07:30 Tehran
    asia = 3.5 <= time_val <= 7.5
    # London Session: 10:30 - 13:30
    london = 10.5 <= time_val <= 13.5
    # NY Session: 16:00 - 19:00  
    ny = 16.0 <= time_val <= 19.0
    # NY Close: 21:00 - 22:00
    ny_close = 21.0 <= time_val <= 22.0
    
    # Crypto weekend (Fri 22:00 - Sun 22:00 Tehran) - often volatile
    is_weekend = dt.weekday() >= 4  # Friday evening onward
    
    return {
        "in_killzone": asia or london or ny or ny_close,
        "asia": asia,
        "london": london,
        "ny": ny,
        "ny_close": ny_close,
        "is_weekend": is_weekend,
        "current_time": f"{hour:02d}:{minute:02d}"
    }


def detect_fvg(candles, direction="bullish", lookback=20):
    """تشخیص Fair Value Gap (FVG)
    
    Bullish FVG: low[i] > high[i-2] (-gap صعودی)
    Bearish FVG: high[i] < low[i-2] (-gap نزولی)
    
    Returns: list of FVGs with price levels
    """
    fvgs = []
    n = len(candles)
    start = max(0, n - lookback)
    
    for i in range(start + 2, n):
        c = candles[i]
        c_minus_2 = candles[i-2]
        
        if direction == "bullish":
            # Bullish FVG: Low of i > High of i-2
            if c["low"] > c_minus_2["high"]:
                fvgs.append({
                    "type": "bullish",
                    "top": c["low"],
                    "bottom": c_minus_2["high"],
                    "index": i,
                })
        else:
            # Bearish FVG: High of i < Low of i-2
            if c["high"] < c_minus_2["low"]:
                fvgs.append({
                    "type": "bearish",
                    "top": c_minus_2["low"],
                    "bottom": c["high"],
                    "index": i,
                })
    
    return fvgs


def detect_order_blocks(candles, direction="bullish", lookback=30):
    """تشخیص Order Block (OB)
    
    Bullish OB: آخرین کندل نزولی (bearish) قبل از حرکت صعودی قوی
    Bearish OB: آخرین کندل صعودی (bullish) قبل از حرکت نزولی قوی
    
    Returns: list of OBs with price levels
    """
    obs = []
    n = len(candles)
    start = max(0, n - lookback)
    
    for i in range(start + 1, n - 1):
        c = candles[i]
        c_next = candles[i+1]
        
        # Bullish OB: candle i bearish, candle i+1 strongly bullish
        if direction == "bullish":
            c_bearish = c["close"] < c["open"]
            next_bullish_strong = (c_next["close"] - c_next["open"]) > abs(c["open"] - c["close"]) * 1.5
            next_bullish = c_next["close"] > c_next["open"]
            
            if c_bearish and next_bullish and next_bullish_strong:
                obs.append({
                    "type": "bullish",
                    "high": c["high"],
                    "low": c["low"],
                    "index": i,
                })
        else:
            # Bearish OB: candle i bullish, candle i+1 strongly bearish
            c_bullish = c["close"] > c["open"]
            next_bearish_strong = (c_next["open"] - c_next["close"]) > abs(c["open"] - c["close"]) * 1.5
            next_bearish = c_next["close"] < c_next["open"]
            
            if c_bullish and next_bearish and next_bearish_strong:
                obs.append({
                    "type": "bearish",
                    "high": c["high"],
                    "low": c["low"],
                    "index": i,
                })
    
    return obs


def detect_liquidity_sweep(candles, direction="bullish", lookback=30):
    """تشخیص Liquidity Sweep
    
    Bullish Sweep: قیمت Swing Low رو می‌شکونه و برمی‌گرده (wick below + close above)
    Bearish Sweep: قیمت Swing High رو می‌شکونه و برمی‌گرده (wick above + close below)
    
    Returns: dict with sweep info or None
    """
    n = len(candles)
    if n < lookback + 5:
        return None
    
    start = max(0, n - lookback)
    recent = candles[start:]
    
    # Find swing highs/lows
    swings_high = []
    swings_low = []
    
    for i in range(2, len(recent) - 2):
        # Swing High
        if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i-2]["high"] and \
           recent[i]["high"] > recent[i+1]["high"] and recent[i]["high"] > recent[i+2]["high"]:
            swings_high.append((i, recent[i]["high"]))
        
        # Swing Low
        if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i-2]["low"] and \
           recent[i]["low"] < recent[i+1]["low"] and recent[i]["low"] < recent[i+2]["low"]:
            swings_low.append((i, recent[i]["low"]))
    
    if not swings_high or not swings_low:
        return None
    
    last_candle = recent[-1]
    
    if direction == "bullish":
        # Bullish sweep: break below last swing low, then close above
        if len(swings_low) >= 2:
            recent_swing_low = swings_low[-1][1]
            prev_swing_low = swings_low[-2][1]
            
            # Wick below swing low but close above
            if last_candle["low"] < prev_swing_low and last_candle["close"] > prev_swing_low:
                return {
                    "type": "bullish",
                    "swept_level": prev_swing_low,
                    "close": last_candle["close"],
                    "wick": last_candle["low"],
                }
    else:
        # Bearish sweep: break above last swing high, then close below
        if len(swings_high) >= 2:
            recent_swing_high = swings_high[-1][1]
            prev_swing_high = swings_high[-2][1]
            
            # Wick above swing high but close below
            if last_candle["high"] > prev_swing_high and last_candle["close"] < prev_swing_high:
                return {
                    "type": "bearish",
                    "swept_level": prev_swing_high,
                    "close": last_candle["close"],
                    "wick": last_candle["high"],
                }
    
    return None


def detect_bos_choch(candles, lookback=50):
    """
    تشخیص BOS (Break of Structure) و CHoCH (Change of Character)
    
    BOS: شکست High/Low قبلی در جهت ترند فعلی = ادامه ترند
    CHoCH: اولین شکست خلاف جهت ترند = تغییر احتمالی ترند
    
    Returns: dict with BOS/CHoCH info
    """
    n = len(candles)
    if n < lookback + 10:
        return None
    
    start = max(0, n - lookback)
    recent = candles[start:]
    
    # Find swing highs and lows (simplified)
    highs = []
    lows = []
    for i in range(2, len(recent) - 2):
        h = recent[i]["high"]
        l = recent[i]["low"]
        if h > recent[i-1]["high"] and h > recent[i-2]["high"] and h > recent[i+1]["high"] and h > recent[i+2]["high"]:
            highs.append((i, h))
        if l < recent[i-1]["low"] and l < recent[i-2]["low"] and l < recent[i+1]["low"] and l < recent[i+2]["low"]:
            lows.append((i, l))
    
    if len(highs) < 3 or len(lows) < 3:
        return None
    
    # Determine recent trend (last 20 candles)
    last_20 = recent[-20:]
    avg_start = sum(c["close"] for c in last_20[:10]) / 10
    avg_end = sum(c["close"] for c in last_20[-10:]) / 10
    recent_trend = "up" if avg_end > avg_start else "down"
    
    # Get last 3 swing points
    last_3_highs = highs[-3:]
    last_3_lows = lows[-3:]
    
    result = {
        "bos_bullish": False,
        "bos_bearish": False,
        "choch_bullish": False,
        "choch_bearish": False,
        "recent_trend": recent_trend,
    }
    
    # BOS Bullish: higher high after higher low (uptrend continuation)
    if len(last_3_highs) >= 2 and len(last_3_lows) >= 2:
        if last_3_highs[-1][1] > last_3_highs[-2][1] and last_3_lows[-1][1] > last_3_lows[-2][1]:
            result["bos_bullish"] = True
            result["bos_level"] = last_3_highs[-2][1]
    
    # BOS Bearish: lower low after lower high (downtrend continuation)
    if len(last_3_highs) >= 2 and len(last_3_lows) >= 2:
        if last_3_lows[-1][1] < last_3_lows[-2][1] and last_3_highs[-1][1] < last_3_highs[-2][1]:
            result["bos_bearish"] = True
            result["bos_level"] = last_3_lows[-2][1]
    
    # CHoCH Bullish: in downtrend, price makes higher low then higher high
    if recent_trend == "down" and len(last_3_lows) >= 2:
        if last_3_lows[-1][1] > last_3_lows[-2][1]:
            result["choch_bullish"] = True
            result["choch_level"] = last_3_lows[-2][1]
    
    # CHoCH Bearish: in uptrend, price makes lower high then lower low
    if recent_trend == "up" and len(last_3_highs) >= 2:
        if last_3_highs[-1][1] < last_3_highs[-2][1]:
            result["choch_bearish"] = True
            result["choch_level"] = last_3_highs[-2][1]
    
    return result


def detect_market_structure_shift(candles, lookback=50):
    """تشخیص Market Structure Shift (MSS)
    
    Bullish MSS: شکست High قبلی (BOS) + Higher Low
    Bearish MSS: شکست Low قبلی (BOS) + Lower High
    
    Returns: dict with MSS info or None
    """
    n = len(candles)
    if n < lookback + 10:
        return None
    
    start = max(0, n - lookback)
    recent = candles[start:]
    
    # Find significant highs and lows
    highs = [(i, c["high"]) for i, c in enumerate(recent)]
    lows = [(i, c["low"]) for i, c in enumerate(recent)]
    
    if len(highs) < 10 or len(lows) < 10:
        return None
    
    # Recent significant levels
    last_10_highs = sorted(highs[-10:], key=lambda x: x[1], reverse=True)
    last_10_lows = sorted(lows[-10:], key=lambda x: x[1])
    
    significant_high = last_10_highs[0][1]
    significant_low = last_10_lows[0][1]
    
    last_close = recent[-1]["close"]
    prev_close = recent[-2]["close"]
    
    result = {"bullish_mss": False, "bearish_mss": False}
    
    # Bullish MSS: close above significant high
    if last_close > significant_high and prev_close <= significant_high:
        result["bullish_mss"] = True
        result["broken_level"] = significant_high
        result["direction"] = "bullish"
    
    # Bearish MSS: close below significant low
    if last_close < significant_low and prev_close >= significant_low:
        result["bearish_mss"] = True
        result["broken_level"] = significant_low
        result["direction"] = "bearish"
    
    return result if (result["bullish_mss"] or result["bearish_mss"]) else None


def find_nearest_fvg(fvgs, current_price, direction="bullish"):
    """پیدا کردن نزدیک‌ترین FVG به قیمت فعلی"""
    if not fvgs:
        return None
    
    if direction == "bullish":
        # For long: find FVG below current price (discount zone)
        valid = [f for f in fvgs if f["bottom"] < current_price]
        if valid:
            return min(valid, key=lambda f: abs(current_price - f["bottom"]))
    else:
        # For short: find FVG above current price (premium zone)
        valid = [f for f in fvgs if f["top"] > current_price]
        if valid:
            return min(valid, key=lambda f: abs(current_price - f["top"]))
    
    return None


def find_nearest_ob(obs, current_price, direction="bullish"):
    """پیدا کردن نزدیک‌ترین Order Block به قیمت فعلی"""
    if not obs:
        return None
    
    if direction == "bullish":
        # For long: find OB below current price
        valid = [o for o in obs if o["high"] < current_price]
        if valid:
            return min(valid, key=lambda o: abs(current_price - o["high"]))
    else:
        # For short: find OB above current price
        valid = [o for o in obs if o["low"] > current_price]
        if valid:
            return min(valid, key=lambda o: abs(current_price - o["low"]))
    
    return None


def ict_analyze(candles_1h, candles_15m=None):
    """تحلیل کامل ICT و برگردوندن امتیاز و دلایل"""
    if not candles_1h or len(candles_1h) < 30:
        return {"score": 0, "reasons": [], "valid": False}
    
    current_price = candles_1h[-1]["close"]
    reasons = []
    ict_score = 0
    
    # 1. Killzone check (informational for crypto 24/7 markets)
    kz = is_ict_killzone()
    if kz["in_killzone"]:
        ict_score += 5  # small bonus for high volatility period
        zone_name = []
        if kz["london"]: zone_name.append("London")
        if kz["ny"]: zone_name.append("NY")
        if kz["ny_close"]: zone_name.append("NY Close")
        reasons.append(f"🌍 زمان کلیدی بازار: {', '.join(zone_name)} ({kz['current_time']})")
    # NOTE: No penalty for being outside killzone - crypto is 24/7
    
    # 2. Detect FVGs for both directions
    fvg_bull = detect_fvg(candles_1h, "bullish", 30)
    fvg_bear = detect_fvg(candles_1h, "bearish", 30)
    
    # 3. Detect OBs
    ob_bull = detect_order_blocks(candles_1h, "bullish", 30)
    ob_bear = detect_order_blocks(candles_1h, "bearish", 30)
    
    # 4. Liquidity sweep
    sweep_bull = detect_liquidity_sweep(candles_1h, "bullish", 30)
    sweep_bear = detect_liquidity_sweep(candles_1h, "bearish", 30)
    
    # 5. Market Structure (MSS + BOS + CHoCH)
    mss = detect_market_structure_shift(candles_1h, 50)
    bos_choch = detect_bos_choch(candles_1h, 50)
    
    # Find nearest levels
    nearest_fvg_bull = find_nearest_fvg(fvg_bull, current_price, "bullish")
    nearest_fvg_bear = find_nearest_fvg(fvg_bear, current_price, "bearish")
    nearest_ob_bull = find_nearest_ob(ob_bull, current_price, "bullish")
    nearest_ob_bear = find_nearest_ob(ob_bear, current_price, "bearish")
    
    # Calculate bullish ICT score
    bull_score = 0
    bull_reasons = []
    
    if nearest_fvg_bull:
        bull_score += 15
        dist = (current_price - nearest_fvg_bull["bottom"]) / current_price * 100
        bull_reasons.append(f"FVG صعودی: قیمت {dist:.1f}% بالای ناحیه عدم تعادل")
    
    if nearest_ob_bull:
        bull_score += 15
        dist = (current_price - nearest_ob_bull["high"]) / current_price * 100
        bull_reasons.append(f"Order Block صعودی: {dist:.1f}% بالای OB")
    
    if sweep_bull:
        bull_score += 20
        bull_reasons.append(f"Liquidity Sweep صعودی: جمع‌آوری نقدینگی زیر swing low")
    
    if mss and mss.get("bullish_mss"):
        bull_score += 20
        bull_reasons.append("Market Structure Shift صعودی: شکست High قبلی")
    
    # BOS/CHoCH bullish
    if bos_choch:
        if bos_choch.get("bos_bullish"):
            bull_score += 15
            bull_reasons.append("🚀 BOS صعودی: Higher High + Higher Low (ادامه ترند)")
        if bos_choch.get("choch_bullish"):
            bull_score += 20
            bull_reasons.append("🔄 CHoCH صعودی: تغییر جهت از نزولی به صعودی!")
    
    # Calculate bearish ICT score
    bear_score = 0
    bear_reasons = []
    
    if nearest_fvg_bear:
        bear_score += 15
        dist = (nearest_fvg_bear["top"] - current_price) / current_price * 100
        bear_reasons.append(f"FVG نزولی: قیمت {dist:.1f}% زیر ناحیه عدم تعادل")
    
    if nearest_ob_bear:
        bear_score += 15
        dist = (nearest_ob_bear["low"] - current_price) / current_price * 100
        bear_reasons.append(f"Order Block نزولی: {dist:.1f}% زیر OB")
    
    if sweep_bear:
        bear_score += 20
        bear_reasons.append(f"Liquidity Sweep نزولی: جمع‌آوری نقدینگی بالای swing high")
    
    if mss and mss.get("bearish_mss"):
        bear_score += 20
        bear_reasons.append("Market Structure Shift نزولی: شکست Low قبلی")
    
    # BOS/CHoCH bearish
    if bos_choch:
        if bos_choch.get("bos_bearish"):
            bear_score += 15
            bear_reasons.append("🔻 BOS نزولی: Lower Low + Lower High (ادامه ترند)")
        if bos_choch.get("choch_bearish"):
            bear_score += 20
            bear_reasons.append("🔄 CHoCH نزولی: تغییر جهت از صعودی به نزولی!")
    
    # Determine best direction
    if bull_score >= bear_score and bull_score > 0:
        ict_score += bull_score
        reasons.extend(bull_reasons)
        preferred_direction = "LONG"
    elif bear_score > bull_score and bear_score > 0:
        ict_score += bear_score
        reasons.extend(bear_reasons)
        preferred_direction = "SHORT"
    else:
        preferred_direction = "NEUTRAL"
        reasons.append("هیچ ستاپ ICT قوی پیدا نشد")
    
    # 15m confirmation
    if candles_15m and len(candles_15m) >= 30:
        fvg_15m_bull = detect_fvg(candles_15m, "bullish", 20)
        fvg_15m_bear = detect_fvg(candles_15m, "bearish", 20)
        
        if preferred_direction == "LONG" and fvg_15m_bull:
            ict_score += 5
            reasons.append("تایید 15m: FVG صعودی در تایم‌فریم پایین‌تر")
        elif preferred_direction == "SHORT" and fvg_15m_bear:
            ict_score += 5
            reasons.append("تایید 15m: FVG نزولی در تایم‌فریم پایین‌تر")
    
    # Valid if score >= 40 (strong ICT setup)
    # NOTE: Killzone is informational only for crypto 24/7 markets
    valid = ict_score >= 40
    
    return {
        "score": min(ict_score, 100),
        "reasons": reasons,
        "valid": valid,
        "direction": preferred_direction,
        "killzone": kz,
        "fvg_bull": len(fvg_bull),
        "fvg_bear": len(fvg_bear),
        "ob_bull": len(ob_bull),
        "ob_bear": len(ob_bear),
        "has_sweep": sweep_bull is not None or sweep_bear is not None,
        "mss": mss,
        "bos_choch": bos_choch,
    }


def format_persian_time(timestamp=None):
    """فرمت فارسی زمان تهران (شمسی)"""
    dt = get_tehran_time(timestamp)
    
    # تبدیل به تاریخ شمسی
    jalali = jdatetime.date.fromgregorian(date=dt.date())
    
    # نام ماه‌های فارسی
    persian_months = {
        1: "فروردین", 2: "اردیبهشت", 3: "خرداد",
        4: "تیر", 5: "مرداد", 6: "شهریور",
        7: "مهر", 8: "آبان", 9: "آذر",
        10: "دی", 11: "بهمن", 12: "اسفند"
    }
    
    # نام روزهای فارسی
    persian_days = {
        0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه",
        3: "پنج‌شنبه", 4: "جمعه", 5: "شنبه", 6: "یکشنبه"
    }
    
    day_name = persian_days.get(dt.weekday(), "")
    month_name = persian_months.get(jalali.month, "")
    
    return f"{day_name} {jalali.day} {month_name} - {dt.hour:02d}:{dt.minute:02d}"


def format_persian_datetime_short(timestamp=None):
    """فرمت کوتاه: ساعت:دقیقه"""
    dt = get_tehran_time(timestamp)
    return f"{dt.hour:02d}:{dt.minute:02d}"


def get_position_times():
    """محاسبه زمان‌های ورود، هشدار و خروج"""
    now = time.time()
    entry_time = now
    exit_time = now + (MAX_POSITION_DURATION_HOURS * 3600)
    warning_time = exit_time - (POSITION_EXPIRY_WARNING_MINUTES * 60)
    
    return {
        'entry': format_persian_time(entry_time),
        'entry_short': format_persian_datetime_short(entry_time),
        'exit': format_persian_time(exit_time),
        'exit_short': format_persian_datetime_short(exit_time),
        'warning': format_persian_time(warning_time),
        'warning_short': format_persian_datetime_short(warning_time),
        'duration_hours': MAX_POSITION_DURATION_HOURS,
    }


class SignalEngine:
    """موتور ترکیب سیگنال‌ها و تولید سیگنال نهایی"""

    def __init__(self, market_data):
        self.market = market_data
        self.order_flow = OrderFlowAnalyzer()
        self.liquidity = LiquidityScanner()
        self.whale = WhaleScanner()
        self.whale_hunter = WhaleHunter()
        self.pre_movement = PreMovementDetector()  # تشخیص قبل از حرکت
        self.zone_hunter = ZoneHunter()  # ZoneHunter indicator
        self.order_flow_matrix = OrderFlowMatrix()  # Order Flow Imbalance Matrix PRO
        self.market_context = MarketContextAnalyzer()  # BTC trend + Market Regime
        self.funding_oi = FundingOIAnalyzer()  # Funding Rate + Open Interest
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

            # اسکن پیشرفته نهنگ (Whale Hunter)
            current_price = candles_1h[-1]["close"]
            whale_hunter_result = self.whale_hunter.analyze_order_book_for_whales(
                order_book, current_price, symbol
            )
            pump_dump_setup = self.whale_hunter.detect_pump_dump_setup(
                candles_1h, order_book
            )
            whale_zones = self.whale_hunter.find_whale_entry_zones(
                candles_1h, order_book
            )

            # اسکن قبل از حرکت (Pre-Movement Detection)
            pre_movement = self.pre_movement.analyze_pre_movement(
                candles_1h, order_book, current_price
            )

            # تحلیل ZoneHunter (Triple SuperTrend + TTD + VWAP Divergence)
            zone_hunter_result = self.zone_hunter.analyze(
                candles=candles_1h,
                candles_4h=candles_4h if candles_4h else None,
            )

            # تحلیل Order Flow Imbalance Matrix PRO
            of_matrix_result = self.order_flow_matrix.analyze(
                candles_1h=candles_1h,
                candles_4h=candles_4h if candles_4h else None,
                current_price=current_price,
            )

            # تحلیل زمینه بازار (BTC Trend + Market Regime + Correlation)
            btc_candles = self.market.get_candles("BTCUSDT", "1h", 200)
            market_ctx = self.market_context.analyze(
                symbol_candles=candles_1h,
                btc_candles=btc_candles if btc_candles else None,
            )

            # تحلیل Funding Rate + Open Interest
            funding_oi_result = self.funding_oi.analyze(symbol)

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
                whale_hunter=whale_hunter_result,
                pump_dump_setup=pump_dump_setup,
                whale_zones=whale_zones,
                pre_movement=pre_movement,
                zone_hunter=zone_hunter_result,
                order_flow_matrix=of_matrix_result,
                market_context=market_ctx,
                funding_oi=funding_oi_result,
                is_shitcoin=is_shitcoin,
            )

            return signal

        except Exception as e:
            logger.error(f"خطا در اسکن {symbol}: {e}")
            return None

    def _generate_signal(self, symbol, base, candles_1h, candles_15m,
                         of_result, trade_flow, sr, pools, book_walls,
                         whale_trades, vol_anomalies, cvd, of_4h,
                         whale_hunter=None, pump_dump_setup=None, whale_zones=None,
                         pre_movement=None, zone_hunter=None, order_flow_matrix=None,
                         market_context=None, funding_oi=None,
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
                liq_score += 20  # وزن بیشتر برای نزدیکی S/R
                reasons.append(f"نزدیک حمایت ({support_dist:.1f}% فاصله)")
            # اگه نزدیک مقاومت باشه = فرصت فروش
            elif resistance_dist < 3:
                direction_votes["SHORT"] += 2
                liq_score -= 20  # وزن بیشتر برای نزدیکی S/R
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

        # === 8. ICT Analysis (Michael Huddleston Strategy) ===
        ict_result = ict_analyze(candles_1h, candles_15m)
        ict_score = ict_result.get("score", 0)
        ict_valid = ict_result.get("valid", False)
        ict_direction = ict_result.get("direction", "NEUTRAL")
        ict_reasons = ict_result.get("reasons", [])
        
        scores.append(("ICT", ict_score))
        
        # ICT direction votes (heavy weight for high win rate)
        if ict_direction == "LONG":
            direction_votes["LONG"] += 4  # وزن بالا برای ICT
            reasons.extend(ict_reasons)
        elif ict_direction == "SHORT":
            direction_votes["SHORT"] += 4
            reasons.extend(ict_reasons)
        else:
            reasons.append("⚠️ هیچ ستاپ ICT قوی پیدا نشد - سیگنال احتمالاً ضعیف")
        
        # Killzone info (informational only for crypto 24/7)
        kz = ict_result.get("killzone", {})
        if kz.get("in_killzone", False):
            zone_name = []
            if kz.get("london"): zone_name.append("London")
            if kz.get("ny"): zone_name.append("NY")
            if kz.get("ny_close"): zone_name.append("NY Close")
            if zone_name:
                reasons.append(f"🌍 زمان کلیدی بازار: {', '.join(zone_name)} (نوسان بالاتر)")

        # === 9. Whale Hunter Analysis (Advanced Whale Detection) ===
        if whale_hunter:
            wh_score = whale_hunter.get("score", 50)
            wh_pressure = whale_hunter.get("whale_pressure", "neutral")
            scores.append(("WhaleHunter", wh_score))
            
            # Whale pressure votes
            if wh_pressure == "buy":
                direction_votes["LONG"] += 3
                reasons.extend(whale_hunter.get("reasons", [])[:2])
            elif wh_pressure == "sell":
                direction_votes["SHORT"] += 3
                reasons.extend(whale_hunter.get("reasons", [])[:2])
            
            # Mega wall alerts
            support = whale_hunter.get("support_wall")
            resistance = whale_hunter.get("resistance_wall")
            if support and support.get("level") == "mega":
                reasons.append(f"🐋 MEGA WALL خرید: ${support['value_usdt']/1e6:.1f}M @ {support['price']:.2f}")
            if resistance and resistance.get("level") == "mega":
                reasons.append(f"🐋 MEGA WALL فروش: ${resistance['value_usdt']/1e6:.1f}M @ {resistance['price']:.2f}")
        
        # Pump/Dump setup detection
        if pump_dump_setup:
            setup_type = pump_dump_setup.get("setup", "none")
            setup_conf = pump_dump_setup.get("confidence", 0)
            if setup_type == "pump" and setup_conf >= 40:
                direction_votes["LONG"] += 3
                reasons.append(f"🚀 ستاپ پمپ شناسایی شد! (confidence: {setup_conf}%)")
                reasons.extend(pump_dump_setup.get("reasons", [])[:2])
            elif setup_type == "dump" and setup_conf >= 40:
                direction_votes["SHORT"] += 3
                reasons.append(f"🔻 ستاپ دامپ شناسایی شد! (confidence: {setup_conf}%)")
                reasons.extend(pump_dump_setup.get("reasons", [])[:2])

        # === 10. Pre-Movement Detection (قبل از حرکت) ===
        if pre_movement:
            pm_conf = pre_movement.get("confidence", 0)
            pm_dir = pre_movement.get("direction", "NEUTRAL")
            pm_signals = pre_movement.get("signals_count", 0)
            
            if pm_dir != "NEUTRAL" and pm_conf >= 50:
                scores.append(("PreMovement", pm_conf))
                
                if pm_dir == "LONG":
                    direction_votes["LONG"] += 4
                    reasons.append(f"⚡ **Pre-Movement LONG** (confidence: {pm_conf}%)")
                elif pm_dir == "SHORT":
                    direction_votes["SHORT"] += 4
                    reasons.append(f"⚡ **Pre-Movement SHORT** (confidence: {pm_conf}%)")
                
                # جزئیات
                reasons.extend(pre_movement.get("reasons", [])[:3])
                
                # RSI divergence details
                rsi_div = pre_movement.get("rsi_divergence", {})
                if rsi_div.get("type") != "none":
                    reasons.append(f"   📊 RSI: {rsi_div.get('current_rsi', 0):.1f} | {rsi_div.get('type', '')}")
                
                # Volume climax
                vol_cl = pre_movement.get("volume_climax", {})
                if vol_cl.get("climax"):
                    reasons.append(f"   📈 Volume: {vol_cl.get('volume_ratio', 0):.1f}x میانگین")

        # === 11. Order Flow Imbalance Matrix PRO ===
        if order_flow_matrix:
            ofm_score = order_flow_matrix.get("score", 50)
            ofm_dir = order_flow_matrix.get("direction", "NEUTRAL")
            ofm_reasons = order_flow_matrix.get("reasons", [])
            ofm_all_agree = order_flow_matrix.get("all_agree", False)
            
            scores.append(("OF Matrix", ofm_score))
            
            if ofm_dir == "LONG":
                direction_votes["LONG"] += 2.5
                reasons.extend(ofm_reasons[:3])
            elif ofm_dir == "SHORT":
                direction_votes["SHORT"] += 2.5
                reasons.extend(ofm_reasons[:3])
            
            # All 3 components agree = strong signal
            if ofm_all_agree:
                reasons.append("🎯 Order Flow Matrix: هر 3 سیستم هم‌جهت!")
                ofm_score += 10
            
            # HTF Levels
            htf = order_flow_matrix.get("htf_levels", {})
            if htf.get("signals"):
                for s in htf["signals"][:1]:
                    reasons.append(f"   {s}")
            
            # Imbalance Zones
            imb = order_flow_matrix.get("imbalance_zones", {})
            if imb.get("inside_zone"):
                reasons.append("💎 قیمت داخل Imbalance Zone نهادی")
            
            # ATR Ribbon
            ribbon = order_flow_matrix.get("atr_ribbon", {})
            if ribbon.get("signals"):
                for s in ribbon["signals"][:1]:
                    reasons.append(f"   {s}")

        # === 12. ZoneHunter Analysis (Triple SuperTrend + TTD + VWAP) ===
        if zone_hunter:
            zh_score = zone_hunter.get("score", 50)
            zh_dir = zone_hunter.get("direction", "NEUTRAL")
            zh_signals = zone_hunter.get("signals_count", 0)
            zh_reasons = zone_hunter.get("reasons", [])
            
            scores.append(("ZoneHunter", zh_score))
            
            if zh_dir == "LONG":
                direction_votes["LONG"] += 3
                reasons.extend(zh_reasons[:3])
            elif zh_dir == "SHORT":
                direction_votes["SHORT"] += 3
                reasons.extend(zh_reasons[:3])
            
            # Triple SuperTrend alignment bonus
            triple_st = zone_hunter.get("triple_supertrend", {})
            if triple_st.get("alignment") in ["strong_bullish", "strong_bearish"]:
                reasons.append(f"🎯 Triple SuperTrend aligned: {triple_st.get('alignment')}")
            
            # TTD alignment
            ttd = zone_hunter.get("ttd", {})
            if ttd.get("alignment") in ["strong_bullish", "strong_bearish"]:
                ttf_aligned = ttd.get("timeframe_trends", {})
                reasons.append(f"📊 TTD: {len([t for t,v in ttf_aligned.items() if v == ttd.get('alignment', '').replace('strong_', '')])} timeframes aligned")
            
            # VWAP Divergence
            vwap_div = zone_hunter.get("vwap_divergence", {})
            if vwap_div.get("divergence"):
                reasons.append(f"💎 VWAP Divergence: {vwap_div.get('type', '')}")

        # === 13. Market Context (BTC Trend + Regime + Correlation) ===
        if market_context:
            ctx_signals = market_context.get("signals", [])
            ctx_score = market_context.get("context_score", 50)
            scores.append(("Market Context", ctx_score))
            reasons.extend(ctx_signals[:3])
            
            # Regime info
            regime = market_context.get("regime", {})
            if regime.get("regime") == "ranging":
                reasons.append(f"↔️ بازار رنج (ADX: {regime.get('adx')}) - فقط ستاپ‌های قوی قبول میشن")

        # === 14. Funding Rate + Open Interest ===
        if funding_oi:
            funding_signals = funding_oi.get("signals", [])
            funding_score = funding_oi.get("sentiment_score", 50)
            scores.append(("Funding/OI", funding_score))
            reasons.extend(funding_signals[:2])

        # === تصمیم نهایی با امتیازدهی وزن‌دار ===
        # Weighted scoring system
        weights = {
            "Order Flow": 1.5,
            "Trade Flow": 1.0,
            "Liquidity/SR": 1.0,
            "Order Book": 1.0,
            "Whale": 1.0,
            "CVD": 1.2,
            "4H Trend": 1.3,
            "ICT": 1.5,
            "WhaleHunter": 1.2,
            "PreMovement": 1.5,
            "OF Matrix": 1.3,
            "ZoneHunter": 1.0,
            "Market Context": 2.0,  # Highest weight - BTC is king
            "Funding/OI": 1.3,
        }
        
        weighted_sum = 0
        weight_total = 0
        for name, score in scores:
            w = weights.get(name, 1.0)
            weighted_sum += score * w
            weight_total += w
        
        total_score = weighted_sum / weight_total if weight_total > 0 else 50

        # تعیین جهت
        # با داده KuCoin (100 ترید، تخمین takerBuyVolume)، آستانه رأی پایین‌تر
        vote_threshold = 2  # هم برای شت‌کوین هم ارز اصلی - 2 رأی کافیه

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

        # اگه امتیاز کافی نبود یا جهت خنثی بود یا ICT ضعیف بود
        if direction == "NEUTRAL" or total_score < min_score:
            reasons.append(f"سیگنال رد شد: امتیاز={total_score:.0f}، حداقل={min_score}")
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
        
        # ICT validation check (must have valid ICT setup for 95%+ win rate)
        if not ict_valid:
            reasons.append(f"سیگنال رد شد: ICT setup ضعیف (score={ict_score:.0f}) - نیاز به FVG/OB/Sweep/MSS قوی")
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
                    "ict": ict_result,
                },
            }
        
        # Direction must match ICT direction for confirmation
        if ict_direction != "NEUTRAL" and direction != ict_direction:
            reasons.append(f"سیگنال رد شد: جهت ({direction}) با ICT ({ict_direction}) همخوانی ندارد")
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
                    "ict": ict_result,
                },
            }
        
        # === Market Context Direction Filter ===
        if market_context and direction != "NEUTRAL":
            ctx_filter = market_context.get("direction_filter")
            if ctx_filter and direction != ctx_filter:
                reasons.append(f"🚫 سیگنال {direction} رد شد: برخلاف جهت BTC/Correlation ({ctx_filter})")
                return {
                    "symbol": symbol,
                    "base": base or symbol,
                    "direction": "NEUTRAL",
                    "score": total_score,
                    "reasons": reasons,
                    "is_shitcoin": is_shitcoin,
                    "analysis": {"market_context": market_context, "filtered": True, "scores": scores},
                }
        
        # === Funding/OI Direction Filter ===
        if funding_oi and direction != "NEUTRAL":
            funding_filter = funding_oi.get("direction_filter")
            if funding_filter and direction != funding_filter:
                reasons.append(f"🚫 سیگنال {direction} رد شد: برخلاف Funding Sentiment ({funding_filter})")
                return {
                    "symbol": symbol,
                    "base": base or symbol,
                    "direction": "NEUTRAL",
                    "score": total_score,
                    "reasons": reasons,
                    "is_shitcoin": is_shitcoin,
                    "analysis": {"funding_oi": funding_oi, "filtered": True, "scores": scores},
                }
        
        # === FOMO Prevention ===
        # Don't enter after a huge candle (chasing = getting rekt)
        last_candle = candles_1h[-1]
        prev_candle = candles_1h[-2]
        last_body_pct = abs(last_candle["close"] - last_candle["open"]) / last_candle["open"] * 100
        prev_body_pct = abs(prev_candle["close"] - prev_candle["open"]) / prev_candle["open"] * 100
        
        # For LONG: don't enter after huge green candle
        if direction == "LONG":
            last_green = last_candle["close"] > last_candle["open"]
            if last_green and last_body_pct > (5.0 if is_shitcoin else 3.0):
                reasons.append(f"سیگنال رد شد: کندل قبلی خیلی بزرگ بود ({last_body_pct:.1f}%) - FOMO!")
                reasons.append("💡 صبر کن برای پولبک، الان ورود = استاپ خوردن")
                return {
                    "symbol": symbol,
                    "base": base or symbol,
                    "direction": "NEUTRAL",
                    "score": total_score,
                    "reasons": reasons,
                    "is_shitcoin": is_shitcoin,
                    "analysis": {"fomo": True, "last_candle_body": last_body_pct},
                }
        
        # For SHORT: don't enter after huge red candle
        if direction == "SHORT":
            last_red = last_candle["close"] < last_candle["open"]
            if last_red and last_body_pct > (5.0 if is_shitcoin else 3.0):
                reasons.append(f"سیگنال رد شد: کندل قبلی خیلی بزرگ بود ({last_body_pct:.1f}%) - FOMO!")
                reasons.append("💡 صبر کن برای پولبک، الان ورود = استاپ خوردن")
                return {
                    "symbol": symbol,
                    "base": base or symbol,
                    "direction": "NEUTRAL",
                    "score": total_score,
                    "reasons": reasons,
                    "is_shitcoin": is_shitcoin,
                    "analysis": {"fomo": True, "last_candle_body": last_body_pct},
                }

        # === محاسبه Entry, SL, TP, Leverage ===
        entry, stop_loss, take_profits, rr, expected_profit, leverage = self._calculate_levels(
            current_price, direction, sr, pools, book_walls, is_shitcoin
        )

        # معیارهای متفاوت برای فیوچر vs spot، و شت‌کوین vs اصلی
        if SIGNAL_TYPE == "futures":
            min_rr = 1.5  # حداقل R:R برای فیوچر (کاهش برای سیگنال‌های بیشتر)
            min_profit = MIN_FUTURES_PROFIT_SHITCOIN if is_shitcoin else MIN_FUTURES_PROFIT_MAIN
        else:
            min_rr = 1.2 if is_shitcoin else MIN_RISK_REWARD
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
            "entry_time": format_persian_time(time.time()),
            "entry_time_short": format_persian_datetime_short(time.time()),
            "exit_time": format_persian_time(time.time() + MAX_POSITION_DURATION_HOURS * 3600),
            "exit_time_short": format_persian_datetime_short(time.time() + MAX_POSITION_DURATION_HOURS * 3600),
            "warning_time": format_persian_time(time.time() + (MAX_POSITION_DURATION_HOURS * 3600) - (POSITION_EXPIRY_WARNING_MINUTES * 60)),
            "warning_time_short": format_persian_datetime_short(time.time() + (MAX_POSITION_DURATION_HOURS * 3600) - (POSITION_EXPIRY_WARNING_MINUTES * 60)),
            "max_duration_hours": MAX_POSITION_DURATION_HOURS,
            "ict_analysis": ict_result,
            "whale_hunter": whale_hunter,
            "pump_dump_setup": pump_dump_setup,
            "whale_zones": whale_zones,
            "pre_movement": pre_movement,
            "zone_hunter": zone_hunter,
            "order_flow_matrix": order_flow_matrix,
            "market_context": market_context,
            "funding_oi": funding_oi,
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
            if risk <= 0 or entry <= 0:
                # اگه ریسک صفر یا منفی باشه، استاپ پیش‌فرض
                stop_loss = entry * 0.97 if direction == "LONG" else entry * 1.03
                risk = abs(entry - stop_loss)

            # Take Profit - برای فیوچر اهداف بالاتر
            if SIGNAL_TYPE == "futures":
                tp_ratios = FUTURES_TP_RATIOS_SHITCOIN if is_shitcoin else FUTURES_TP_RATIOS
            else:
                tp_ratios = [2.0, 4.0, 7.0] if is_shitcoin else TP_RATIOS
            take_profits = []
            for ratio in tp_ratios[:TP_LEVELS]:
                tp = entry + (risk * ratio)
                take_profits.append(round(tp, 8))

            expected_profit = (take_profits[-1] - entry) / entry * 100 if entry > 0 else 0

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
            if risk <= 0 or entry <= 0:
                stop_loss = entry * 1.03
                risk = stop_loss - entry

            if SIGNAL_TYPE == "futures":
                tp_ratios = FUTURES_TP_RATIOS_SHITCOIN if is_shitcoin else FUTURES_TP_RATIOS
            else:
                tp_ratios = [2.0, 4.0, 7.0] if is_shitcoin else TP_RATIOS
            take_profits = []
            for ratio in tp_ratios[:TP_LEVELS]:
                tp = entry - (risk * ratio)
                take_profits.append(round(tp, 8))

            expected_profit = (entry - take_profits[-1]) / entry * 100 if entry > 0 else 0

        risk_reward = tp_ratios[-1] if 'tp_ratios' in locals() and tp_ratios else TP_RATIOS[-1]

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
        
        # محاسبه ریسک واقعی با اهرم
        risk_with_leverage = sl_pct * leverage
        
        # سایز پوزیشن بر اساس 2% رول
        # Risk = 2% of account / stop loss %
        position_size_1000 = (1000 * 0.02) / (sl_pct / 100) if sl_pct > 0 else 0
        position_size_500 = (500 * 0.02) / (sl_pct / 100) if sl_pct > 0 else 0
        position_size_100 = (100 * 0.02) / (sl_pct / 100) if sl_pct > 0 else 0

        # قیمت لیکویید تقریبی (با اهرم)
        if direction == "LONG":
            liq_price = entry * (1 - 1.0 / leverage * 0.95)
        else:
            liq_price = entry * (1 + 1.0 / leverage * 0.95)

        msg = f"""
{emoji} سیگنال فیوچر {direction} - {base}{tag} {emoji}"""

        # شت‌کوین warning
        if is_shitcoin:
            msg += """

🚨 **هشدار شت‌کوین** 🚨
⚠️ این ارز نوسان خیلی بالایی داره!
⚠️ فقط با پولی وارد شو که توانایی از دست دادنش رو داری
⚠️ هرگز اهرم بالاتر از توصیه شده استفاده نکن!"""

        msg += f"""

📊 امتیاز: {score:.0f}/100
⚡ اهرم توصیه شده: **{leverage}x** (بیشتر نزن!)
💰 ورود: {fmt(entry)}
🛑 استاپ لاس: {fmt(stop_loss)} ({sl_pct:.1f}%)
💀 قیمت لیکویید: {fmt(liq_price)}
📉 ریسک با اهرم: {risk_with_leverage:.0f}%"""

        for i, tp in enumerate(take_profits, 1):
            tp_pct = abs(tp - entry) / entry * 100
            msg += f"\n🎯 هدف {i}: {fmt(tp)} (+{tp_pct:.1f}%)"

        msg += f"""

📐 Risk/Reward: {rr:.1f}:1
📈 سود مورد انتظار: {expected_profit:.1f}%
💰 سود با اهرم {leverage}x: ~{expected_profit * leverage:.0f}%

💵 **سایز پوزیشن (ریسک 2%):**
💰 اگه سرمایه‌ت $1000 → پوزیشن: ${position_size_1000:.0f}
💰 اگه سرمایه‌ت $500 → پوزیشن: ${position_size_500:.0f}
💰 اگه سرمایه‌ت $100 → پوزیشن: ${position_size_100:.0f}

📊 ICT Strategy (Michael Huddleston):
🎯 وین ریت هدف: 95%+
📈 حداقل سود: 70%+
🌐 کریپتو 24/7 - سیگنال در هر ساعت فعال

📋 دلایل سیگنال:
"""
        for r in reasons:
            msg += f"  • {r}\n"
        
        # ICT details
        ict = signal.get('ict_analysis', {})
        if ict:
            msg += "\n🔷 ICT Confirmations:\n"
            if ict.get('fvg_bull', 0) > 0 or ict.get('fvg_bear', 0) > 0:
                msg += f"  ✓ Fair Value Gap detected\n"
            if ict.get('ob_bull', 0) > 0 or ict.get('ob_bear', 0) > 0:
                msg += f"  ✓ Order Block detected\n"
            if ict.get('has_sweep', False):
                msg += f"  ✓ Liquidity Sweep confirmed\n"
            if ict.get('mss'):
                msg += f"  ✓ Market Structure Shift\n"
            
            bc = ict.get('bos_choch', {})
            if bc:
                if bc.get('bos_bullish'):
                    msg += f"  ✓ BOS Bullish: Higher High\n"
                elif bc.get('bos_bearish'):
                    msg += f"  ✓ BOS Bearish: Lower Low\n"
                if bc.get('choch_bullish'):
                    msg += f"  ✓ CHoCH Bullish: Trend Reversal Up\n"
                elif bc.get('choch_bearish'):
                    msg += f"  ✓ CHoCH Bearish: Trend Reversal Down\n"
            
            kz = ict.get('killzone', {})
            if kz.get('in_killzone'):
                zones = []
                if kz.get('asia'): zones.append('Asia')
                if kz.get('london'): zones.append('London')
                if kz.get('ny'): zones.append('NY')
                if kz.get('ny_close'): zones.append('NY Close')
                msg += f"  🌍 سشن فعال: {', '.join(zones)}\n"

        # Whale Hunter details
        wh = signal.get('whale_hunter', {})
        if wh:
            msg += "\n🐋 **Whale Hunter Analysis:**\n"
            pressure = wh.get('whale_pressure', 'neutral')
            if pressure == 'buy':
                msg += "  🟢 فشار خرید نهنگی قوی\n"
            elif pressure == 'sell':
                msg += "  🔴 فشار فروش نهنگی قوی\n"
            
            support = wh.get('support_wall')
            if support:
                msg += f"  📗 دیوار حمایت: ${support['value_usdt']/1e6:.1f}M @ {support['price']:.2f}\n"
            
            resistance = wh.get('resistance_wall')
            if resistance:
                msg += f"  📕 دیوار مقاومت: ${resistance['value_usdt']/1e6:.1f}M @ {resistance['price']:.2f}\n"
            
            liq_zones = wh.get('liquidation_zones', [])
            for lz in liq_zones[:2]:
                msg += f"  ⚡ {lz.get('description', '')}\n"

        # Pump/Dump setup
        pds = signal.get('pump_dump_setup', {})
        if pds and pds.get('setup') != 'none':
            setup = pds.get('setup', '')
            conf = pds.get('confidence', 0)
            if setup == 'pump':
                msg += f"\n🚀 **ستاپ پمپ شناسایی شد!** (confidence: {conf}%)\n"
            elif setup == 'dump':
                msg += f"\n🔻 **ستاپ دامپ شناسایی شد!** (confidence: {conf}%)\n"

        # Order Flow Imbalance Matrix PRO
        ofm = signal.get('order_flow_matrix', {})
        if ofm and ofm.get('direction') != 'NEUTRAL':
            ofm_dir = ofm.get('direction', '')
            ofm_score = ofm.get('score', 0)
            ofm_all_agree = ofm.get('all_agree', False)
            msg += f"\n🏛️ **Order Flow Matrix PRO** ({ofm_dir}, score: {ofm_score})\n"
            if ofm_all_agree:
                msg += "   🎯 هر 3 سیستم هم‌جهت! (HTF + Imbalance + Ribbon)\n"
            
            htf = ofm.get('htf_levels', {})
            if htf.get('signals'):
                for s in htf['signals'][:1]:
                    msg += f"   {s}\n"
            
            imb = ofm.get('imbalance_zones', {})
            if imb.get('signals'):
                for s in imb['signals'][:1]:
                    msg += f"   {s}\n"
            
            ribbon = ofm.get('atr_ribbon', {})
            if ribbon.get('signals'):
                for s in ribbon['signals'][:1]:
                    msg += f"   {s}\n"

        # ZoneHunter Analysis
        zh = signal.get('zone_hunter', {})
        if zh and zh.get('direction') != 'NEUTRAL':
            zh_dir = zh.get('direction', '')
            zh_score = zh.get('score', 0)
            msg += f"\n🎯 **ZoneHunter** ({zh_dir}, score: {zh_score})\n"
            
            triple_st = zh.get('triple_supertrend', {})
            if triple_st.get('signals'):
                for s in triple_st['signals'][:1]:
                    msg += f"   {s}\n"
            
            ttd = zh.get('ttd', {})
            if ttd.get('signals'):
                for s in ttd['signals'][:1]:
                    msg += f"   {s}\n"
            
            vwap = zh.get('vwap_divergence', {})
            if vwap.get('signals'):
                for s in vwap['signals'][:1]:
                    msg += f"   {s}\n"

        # Market Context (BTC + Regime + Correlation)
        ctx = signal.get('market_context', {})
        if ctx:
            msg += "\n🌍 **Market Context:**\n"
            
            btc = ctx.get('btc_trend', {})
            if btc.get('trend') != 'unknown':
                msg += f"   ₿ BTC: {btc.get('trend')} (momentum: {btc.get('momentum', 0):+.1f}%)\n"
            
            regime = ctx.get('regime', {})
            if regime.get('regime') != 'unknown':
                msg += f"   📊 Regime: {regime.get('regime')} (ADX: {regime.get('adx')})\n"
            
            corr = ctx.get('correlation', {})
            if corr.get('correlation') != 0:
                msg += f"   🔗 Correlation with BTC: {corr.get('correlation'):.2f} ({corr.get('alignment')})\n"
            
            struct = ctx.get('structure', {})
            if struct.get('structure') != 'unknown':
                msg += f"   📐 Structure: {struct.get('structure')}\n"

        # Funding Rate + Open Interest
        fnd = signal.get('funding_oi', {})
        if fnd and fnd.get('status') == 'active':
            msg += "\n💰 **Funding & Open Interest:**\n"
            rate = fnd.get('funding_rate', 0)
            msg += f"   Funding Rate: {rate*100:.4f}%\n"
            if fnd.get('open_interest'):
                msg += f"   Open Interest: {fnd.get('open_interest'):,.0f}\n"
            
            hist = fnd.get('funding_history', {})
            if hist and hist.get('rates'):
                msg += f"   Funding Trend: {hist.get('trend')}\n"

        # Pre-Movement Detection
        pm = signal.get('pre_movement', {})
        if pm and pm.get('direction') != 'NEUTRAL':
            pm_conf = pm.get('confidence', 0)
            pm_dir = pm.get('direction', '')
            pm_signals = pm.get('signals_count', 0)
            
            msg += f"\n⚡ **Pre-Movement Alert** ({pm_signals} signals, conf: {pm_conf}%)\n"
            
            # RSI Divergence
            rsi_div = pm.get('rsi_divergence', {})
            if rsi_div.get('type') != 'none':
                msg += f"   📊 RSI: {rsi_div.get('current_rsi', 0):.1f} | {rsi_div.get('type', '')}\n"
            
            # Volume Climax
            vol_cl = pm.get('volume_climax', {})
            if vol_cl.get('climax'):
                msg += f"   📈 Volume: {vol_cl.get('volume_ratio', 0):.1f}x average\n"
            
            # Delta Divergence
            delta_div = pm.get('delta_divergence', {})
            if delta_div.get('divergence'):
                msg += f"   💧 Delta Divergence: {delta_div.get('type', '')}\n"
            
            # OB Shift
            ob_shift = pm.get('ob_shift', {})
            if ob_shift.get('shift'):
                msg += f"   📚 OB Imbalance: {ob_shift.get('bid_ratio', 0)*100:.0f}% buy\n"

        entry_time = signal.get('entry_time', '')
        exit_time = signal.get('exit_time', '')
        warning_time = signal.get('warning_time', '')
        max_hours = signal.get('max_duration_hours', 4)

        msg += f"""

⏰ زمان‌بندی پوزیشن (تهران):
🟢 ورود: {entry_time}
🔴 خروج (حداکثر): {exit_time}
⚠️ هشدار: {warning_time}

💡 مدت باز بودن: {max_hours} ساعت
"""
        msg += "\n⚠️ **هشدار:** این سیگنال توسط ربات تولید شده و نظر سرمایه‌گذاری نیست. مسئولیت معامله با شماست."
        msg += "\n🔧 سیگنال فیوچر - حتماً با مدیریت ریسک مناسب وارد شوید."

        return msg
