# -*- coding: utf-8 -*-
"""
تنظیمات بات سیگنال کریپتو
"""

import os

# ===================== تنظیمات تلگرام =====================
# توکن بات تلگرام - از BotFather گرفته شد
# روی سرور ابری، از متغیر محیطی TELEGRAM_BOT_TOKEN استفاده می‌شه
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8763890105:AAGbAQgr75k_kIGU7qgKrdNNo9aPFcqqtC8")

# چت آیدی - به محض /start خودکار تنظیم میشه
# روی سرور، از متغیر محیطی TELEGRAM_CHAT_ID استفاده می‌شه (به صورت رشته)
_chat_id_env = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_ID = int(_chat_id_env) if _chat_id_env else None

# آیدی ادمین‌ها (لیست اعداد)
ADMIN_IDS = []

# ===================== تنظیمات بازار =====================
# صرافی مورد استفاده (Binance API عمومی - نیاز به کلید ندارد برای داده عمومی)
BINANCE_BASE_URL = "https://api.binance.com"

# لیست ارزهایی که اسکن میشن (USDT جفت)
# None = همه ارزهای USDT موجود با حداقل حجم
SCAN_SYMBOLS = None

# ===================== فیلتر صرافی KCEX =====================
# فقط ارزهایی که تو صرافی KCEX موجود هستن اسکن میشن
# لیست از https://www.kcex.com/markets استخراج شده
KCEX_SYMBOLS = [
    # ارزهای اصلی
    "BTCUSDT",    # Bitcoin
    "ETHUSDT",    # Ethereum
    "BNBUSDT",    # BNB
    "XRPUSDT",    # Ripple
    "SOLUSDT",    # Solana
    "TRXUSDT",    # Tron
    "ZECUSDT",    # Zcash
    "HYPEUSDT",   # Hyperliquid
    "LINKUSDT",   # Chainlink
    "ADAUSDT",    # Cardano
    "NEARUSDT",   # Near Protocol
    "XLMUSDT",    # Stellar
    "BCHUSDT",    # Bitcoin Cash
    "LTCUSDT",    # Litecoin
    "UNIUSDT",    # Uniswap
    "AVAXUSDT",   # Avalanche
    "SUIUSDT",    # Sui
    "DOTUSDT",    # Polkadot
    "AAVEUSDT",   # Aave
    "ONDOUSDT",   # Ondo
    "WLDUSDT",    # Worldcoin
    "ENAUSDT",    # Ethena
    "QNTUSDT",    # Quant
    "CROUSDT",    # Cronos
    "ICPUSDT",    # Internet Computer
    "ARBUSDT",    # Arbitrum
    "ETCUSDT",    # Ethereum Classic
    "TAOUSDT",    # Bittensor
    "MNTUSDT",    # Mantle
    "MORPHOUSDT", # Morpho
    "OKBUSDT",    # OKB
    "SKYUSDT",    # Sky
    "ASTERUSDT",  # Aster
    "WLFIUSDT",   # World Liberty Financial
    # استیبل‌کوین‌ها و طلا (می‌خوایم فیلتر بشن، تو لیست برای مرجع)
    # "USDCUSDT", "USD1USDT", "USDSUSDT", "GOLDUSDT"
    # شت‌کوین‌ها و meme coins
    "DOGEUSDT",   # Dogecoin
    "SHIBUSDT",   # Shiba Inu
    "PEPEUSDT",   # Pepe
    "PUMPUSDT",   # Pump Fun
    "MUSDT",      # MemeCore
    "RAINUSDT",   # Rain
    "BTWUSDT",    # Bitway
    "GRAMUSDT",   # Gram
    "CCUSDT",     # Canton Network
]

# اگه True باشه، فقط ارزهای KCEX اسکن میشن
USE_KCEX_FILTER = True

# حداقل حجم معاملات روزانه برای ارزهای اصلی (به USDT)
MIN_24H_VOLUME = 50_000_000  # 50 میلیون دلار

# حداقل حجم معاملات روزانه برای شت‌کوین‌ها (کمتر = ارزهای فرعی‌تر هم اسکن میشن)
MIN_24H_VOLUME_SHITCOIN = 5_000_000  # 5 میلیون دلار

# لیست شت‌کوین‌ها و meme coin‌های معروف که همیشه پایش میشن
# فقط اونایی که تو KCEX هستن
SHITCOIN_SYMBOLS = [
    "DOGEUSDT",   # Dogecoin ✓ KCEX
    "SHIBUSDT",   # Shiba Inu ✓ KCEX
    "PEPEUSDT",   # Pepe ✓ KCEX
    "PUMPUSDT",   # Pump Fun ✓ KCEX
    "MUSDT",      # MemeCore ✓ KCEX
    "RAINUSDT",   # Rain ✓ KCEX
    "BTWUSDT",    # Bitway ✓ KCEX
    "GRAMUSDT",   # Gram ✓ KCEX
    "CCUSDT",     # Canton Network ✓ KCEX
]

# حداقل حجم ترید نهنگ برای شت‌کوین‌ها (کمتر چون حجم کل کمتره)
WHALE_TX_THRESHOLD_SHITCOIN = 100_000  # 100 هزار دلار برای شت‌کوین

# حداقل درصد سود برای سیگنال شت‌کوین (بالاتر چون نوسان بالاتره)
MIN_TARGET_PROFIT_SHITCOIN = 15.0  # 15%

# تایم‌فریم‌های تحلیل
TIMEFRAMES = ["15m", "1h", "4h"]

# تعداد کندل‌هایی که دریافت میشه
CANDLE_LIMIT = 200

# ===================== تنظیمات سیگنال =====================
# حداقل درصد سود مورد انتظار
MIN_TARGET_PROFIT = 10.0  # 10%

# حداقل Risk/Reward
MIN_RISK_REWARD = 2.0

# حداکثر درصد استاپ لاس (نسبت به قیمت ورود)
MAX_STOP_LOSS_PCT = 5.0  # 5%

# فاصله استاپ از قیمت ورود (درصد)
STOP_LOSS_BUFFER = 1.5

# تعداد حد سود (Take Profit)
TP_LEVELS = 3  # سه هدف سود

# ضریب‌های هدف سود نسبت به استاپ
TP_RATIOS = [1.5, 2.5, 4.0]

# ===================== تنظیمات Order Flow =====================
# تعداد کندل‌ها برای تحلیل order flow
ORDER_FLOW_LOOKBACK = 50

# آستانه عدم تعادل خرید/فروش (delta)
DELTA_THRESHOLD = 2.0  # نسبت خرید به فروش باید حداقل 2:1 باشه

# حجم کندل‌های بزرگ (ضریب میانگین)
LARGE_VOLUME_MULTIPLIER = 2.5

# ===================== تنظیمات Liquidity =====================
# تعداد ساعات برای اسکن نقدینگی
LIQUIDITY_LOOKBACK_HOURS = 24

# آستانه شناسایی حمایت/مقاومت (درصد)
SR_ZONE_THRESHOLD = 0.5  # 0.5%

# ===================== تنظیمات نهنگ‌ها =====================
# حداقل حجم تراکنش نهنگ (به USDT)
WHALE_TX_THRESHOLD = 1_000_000  # 1 میلیون دلار

# تعداد تراکنش‌های اخیر نهنگ که بررسی میشه
WHALE_TX_LIMIT = 100

# آستانه فعالیت نهنگ برای سیگنال
WHALE_SIGNAL_THRESHOLD = 3  # حداقل 3 تراکنش نهنگ در جهت مشترک

# ===================== تنظیمات اسکن =====================
# فاصله زمانی بین هر اسکن (ثانیه)
SCAN_INTERVAL = 300  # 5 دقیقه

# زمان‌بندی ارسال سیگنال تکراری (ثانیه - برای جلوگیری از اسپم)
SIGNAL_COOLDOWN = 3600  # 1 ساعت برای هر ارز

# حداقل امتیاز سیگنال برای ارسال
MIN_SIGNAL_SCORE = 70  # از 100

# ===================== لاگ =====================
LOG_LEVEL = "INFO"
LOG_FILE = "bot.log"
