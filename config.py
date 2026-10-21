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

# آیدی ادمین‌ها (لیست اعداد) - فقط این آیدی‌ها می‌تونن از بات استفاده کنن
# چت آیدی اصلی (تو): 7769330487, 8328717485
AUTHORIZED_CHAT_IDS = [7769330487, 8328717485]

# ===================== تنظیمات بازار =====================
# صرافی مورد استفاده (Binance API عمومی - نیاز به کلید ندارد برای داده عمومی)
# data-api.binance.vision بدون محدودیت جغرافیایی (api.binance.com روی Render 451 می‌ده)
BINANCE_BASE_URL = "https://data-api.binance.vision"

# لیست ارزهایی که اسکن میشن (USDT جفت)
# None = همه ارزهای USDT موجود با حداقل حجم
SCAN_SYMBOLS = None

# ===================== فیلتر صرافی KCEX =====================
# فقط ارزهایی که تو صرافی KCEX موجود هستن اسکن میشن
# لیست از https://www.kcex.com/markets استخراج شده
# لیست کامل از https://www.kcex.com/markets استخراج شده (2026-10-19)
# شامل همه ارزهای KCEX (USDT جفت) - هم Spot هم Futures
KCEX_SYMBOLS = [
    # === ارزهای اصلی ===
    "BTCUSDT",    # Bitcoin
    "ETHUSDT",    # Ethereum
    "BNBUSDT",    # BNB
    "XRPUSDT",    # Ripple
    "SOLUSDT",    # Solana
    "TRXUSDT",    # Tron
    "ZECUSDT",    # Zcash
    "HYPEUSDT",   # Hyperliquid
    "XMRUSDT",    # Monero
    "LINKUSDT",   # Chainlink
    "ADAUSDT",    # Cardano
    "NEARUSDT",   # Near Protocol
    "RAINUSDT",   # Rain
    "XLMUSDT",    # Stellar
    "BCHUSDT",    # Bitcoin Cash
    "LTCUSDT",    # Litecoin
    "UNIUSDT",    # Uniswap
    "BTWUSDT",    # Bitway
    "AVAXUSDT",   # Avalanche
    "CCUSDT",     # Canton Network
    "SUIUSDT",    # Sui
    "HBARUSDT",   # Hedera
    "TAOUSDT",    # Bittensor
    "SHIBUSDT",   # Shiba Inu
    "CROUSDT",    # Cronos
    "QNTUSDT",    # Quant
    "ENAUSDT",    # Ethena
    "OKBUSDT",    # OKB
    "AAVEUSDT",   # Aave
    "ONDOUSDT",   # Ondo
    "PUMPUSDT",   # Pump Fun
    "WLDUSDT",    # Worldcoin
    "DOTUSDT",    # Polkadot
    "ASTERUSDT",  # Aster
    "WLFIUSDT",   # World Liberty Financial
    "MNTUSDT",    # Mantle
    "PEPEUSDT",   # Pepe
    "MORPHOUSDT", # Morpho
    "SKYUSDT",    # Sky
    "ICPUSDT",    # Internet Computer
    "MUSDT",      # MemeCore
    "ARBUSDT",    # Arbitrum
    "ETCUSDT",    # Ethereum Classic
    "GRAMUSDT",   # Gram
    # استیبل‌کوین‌ها و طلا (فیلتر می‌شن - نوسان ندارن)
    # "USDCUSDT", "USD1USDT", "USDSUSDT", "GOLDUSDT", "XAUTUSDT", "PAXGUSDT"
]

# اگه True باشه، فقط ارزهای KCEX اسکن میشن
# False = همه ارزهای Binance با حداقل حجم (نزدیک به 300 ارز)
USE_KCEX_FILTER = False

# حداقل حجم معاملات روزانه برای ارزهای اصلی (به USDT)
# کاهش به 500K برای پایش ~300 ارز Binance
MIN_24H_VOLUME = 500_000  # 500 هزار دلار

# حداقل حجم معاملات روزانه برای شت‌کوین‌ها (کمتر = ارزهای فرعی‌تر هم اسکن میشن)
MIN_24H_VOLUME_SHITCOIN = 500_000  # 500 هزار دلار

# لیست شت‌کوین‌ها و meme coin‌های معروف که همیشه پایش میشن
# لیست گسترده شامل مهم‌ترین meme/shitcoin‌های بازار
SHITCOIN_SYMBOLS = [
    # === Meme Coins بزرگ ===
    "DOGEUSDT",   # Dogecoin
    "SHIBUSDT",   # Shiba Inu
    "PEPEUSDT",   # Pepe
    "WIFUSDT",    # dogwifhat
    "BONKUSDT",   # Bonk
    "FLOKIUSDT",  # Floki
    "MEMEUSDT",   # Memecoin
    "BOMEUSDT",   # Book of Meme
    "POPCATUSDT", # Popcat
    "PNUTUSDT",   # Peanut the Squirrel
    "ACTUSDT",    # Act I: The AI prophecy
    "GOATUSDT",   # Goatseus Maximus
    "MOODENGUSDT",# Moo Deng
    "TRUMPUSDT",  # Official Trump
    "MELANIAUSDT",# Melania
    "AI16ZUSDT",  # ai16z
    "VIRTUALUSDT",# Virtuals Protocol
    "SWARMSUSDT", # Swarms
    "NEIROUSDT",  # Neiro
    "TURBOUSDT",  # Turbo
    "ORDIUSDT",   # Ordinals
    "SATSUSDT",   # 1000SATS
    "RATSUSDT",   # Rats
    "MOBILEUSDT", # Helium Mobile
    # === Pump.fun / Meme جدید ===
    "PUMPUSDT",   # Pump Fun
    "MUSDT",      # MemeCore
    "RAINUSDT",   # Rain
    "BTWUSDT",    # Bitway
    "GRAMUSDT",   # Gram
    "CCUSDT",     # Canton Network
    "ASTERUSDT",  # Aster
    "WLFIUSDT",   # World Liberty Financial
    "SKYUSDT",    # Sky
    "MORPHOUSDT",# Morpho
    # === Meme/Community ===
    "1000SATSUSDT",# 1000SATS
    "CHZUSDT",    # Chiliz
    "GALAUSDT",   # Gala
    "MANAUSDT",   # Decentraland
    "SANDUSDT",   # Sandbox
    "AXSUSDT",    # Axie Infinity
    "ALICEUSDT",  # My Neighbor Alice
    "SFPUSDT",    # SafePal
    "LAZIOUSDT",  # Lazio
    "PORTOUSDT",  # Port3
    "CFXUSDT",    # Conflux
    "MASKUSDT",   # Mask
    "DODOUSDT",   # Dodo
    "RVNUSDT",    # Ravencoin
    "DUSKUSDT",   # Dusk
    "KEYUSDT",    # SelfKey
    "NKNUSDT",    # NKN
    "NULSUSDT",   # Nuls
    "VOXELUSDT",  # Voxies
    "GFTUSDT",    # GuildFi
    "COCOSUSDT",  # Cocos
]

# حداقل حجم ترید نهنگ برای شت‌کوین‌ها (کمتر چون حجم کل کمتره)
WHALE_TX_THRESHOLD_SHITCOIN = 50_000  # 50 هزار دلار برای شت‌کوین

# حداقل درصد سود برای سیگنال شت‌کوین
MIN_TARGET_PROFIT_SHITCOIN = 8.0  # 8%

# تایم‌فریم‌های تحلیل
TIMEFRAMES = ["15m", "1h", "4h"]

# تعداد کندل‌هایی که دریافت میشه
CANDLE_LIMIT = 200

# ===================== تنظیمات سیگنال =====================
# حداقل درصد سود مورد انتظار
MIN_TARGET_PROFIT = 5.0  # 5%

# حداقل Risk/Reward
MIN_RISK_REWARD = 1.5

# حداکثر درصد استاپ لاس (نسبت به قیمت ورود)
MAX_STOP_LOSS_PCT = 5.0  # 5%

# فاصله استاپ از قیمت ورود (درصد)
STOP_LOSS_BUFFER = 1.5

# تعداد حد سود (Take Profit)
TP_LEVELS = 3  # سه هدف سود

# ضریب‌های هدف سود نسبت به استاپ
TP_RATIOS = [1.5, 2.5, 4.0]

# ===================== تنظیمات سیگنال فیوچر =====================
# نوع سیگنال: futures (شامل اهرم، حد لیکوییداسیون، و ریسک‌ها)
SIGNAL_TYPE = "futures"

# اهرم پیشنهادی (leverage) - بسته به نوسان ارز
FUTURES_LEVERAGE_MAIN = 10    # ارزهای اصلی (BTC, ETH, etc.)
FUTURES_LEVERAGE_SHITCOIN = 3  # شت‌کوین‌ها = اهرم کمتر (ریسک خیلی بالاست)

# حداکثر درصد استاپ برای فیوچر
MAX_FUTURES_STOP_PCT_MAIN = 5.0       # 5% برای ارزهای اصلی
MAX_FUTURES_STOP_PCT_SHITCOIN = 5.0   # 5% برای شت‌کوین هم (با 3x = 15% max loss)

# TP Ratios
FUTURES_TP_RATIOS = [5.0, 10.0, 15.0]  # RR برای ارزهای اصلی
FUTURES_TP_RATIOS_SHITCOIN = [4.0, 8.0, 12.0]  # RR کمتر برای شت‌کوین

# ===================== Risk Management =====================
# حداکثر ضرر روزانه (به درصد سرمایه)
MAX_DAILY_LOSS_PCT = 10.0  # 10% سرمایه = استاپ تریدینگ

# حداکثر ریسک هر پوزیشن (به درصد سرمایه)
MAX_RISK_PER_POSITION_PCT = 2.0  # 2% سرمایه برای هر پوزیشن

# حداکثر تعداد پوزیشن همزمان
MAX_OPEN_POSITIONS = 3

# ===================== تنظیمات ICT (Inner Circle Trader) =====================
# حداقل سود واقعی قبل از اهرم
MIN_FUTURES_PROFIT_MAIN = 10.0      # 10% واقعی
MIN_FUTURES_PROFIT_SHITCOIN = 12.0  # 12% واقعی

# حداقل امتیاز ICT
MIN_FUTURES_SCORE_MAIN = 50       # 50/100
MIN_FUTURES_SCORE_SHITCOIN = 45   # 45/100

# فقط تایم‌فریم‌های ICT
ICT_TIMEFRAMES = ['1h', '15m']

# ===================== تنظیمات زمان‌بندی پوزیشن =====================
# حداکثر زمان باز بودن پوزیشن (به ساعت)
MAX_POSITION_DURATION_HOURS = 4  # 4 ساعت - هماهنگ با ICT killzone

# هشدار قبل از اتمام زمان (به دقیقه)
POSITION_EXPIRY_WARNING_MINUTES = 30  # 30 دقیقه قبل هشدار بده

# ===================== تنظیمات Order Flow =====================
# تعداد کندل‌ها برای تحلیل order flow
ORDER_FLOW_LOOKBACK = 50

# آستانه عدم تعادل خرید/فروش (delta)
DELTA_THRESHOLD = 1.3  # نسبت خرید به فروش (کاهش از 2.0 به 1.3)

# حجم کندل‌های بزرگ (ضریب میانگین)
LARGE_VOLUME_MULTIPLIER = 2.5

# ===================== تنظیمات Liquidity =====================
# تعداد ساعات برای اسکن نقدینگی
LIQUIDITY_LOOKBACK_HOURS = 24

# آستانه شناسایی حمایت/مقاومت (درصد)
SR_ZONE_THRESHOLD = 0.5  # 0.5%

# ===================== تنظیمات نهنگ‌ها =====================
# حداقل حجم تراکنش نهنگ (به USDT)
WHALE_TX_THRESHOLD = 100_000  # 100K (کاهش از 1M)

# تعداد تراکنش‌های اخیر نهنگ که بررسی میشه
WHALE_TX_LIMIT = 100

# آستانه فعالیت نهنگ برای سیگنال
WHALE_SIGNAL_THRESHOLD = 1  # حداقل 1 تراکنش نهنگ

# ===================== تنظیمات اسکن =====================
# فاصله زمانی بین هر اسکن (ثانیه)
# افزایش به 480 ثانیه (8 دقیقه) چون اسکن 300 ارز زمان بیشتری می‌بره
SCAN_INTERVAL = 480  # 8 دقیقه

# زمان‌بندی ارسال سیگنال تکراری (ثانیه - برای جلوگیری از اسپم)
SIGNAL_COOLDOWN = 3600  # 1 ساعت برای هر ارز

# حداقل امتیاز سیگنال برای ارسال
MIN_SIGNAL_SCORE = 45  # کاهش از 55 به 45

# ===================== لاگ =====================
LOG_LEVEL = "INFO"
LOG_FILE = "bot.log"
