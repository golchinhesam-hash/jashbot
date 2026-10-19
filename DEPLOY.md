# راهنمای اجرای بات روی سرور رایگان (بدون نیاز به لپ‌تاپ روشن)

## چرا سرور ابری؟

الان بات فقط وقتی کار می‌کنه که لپ‌تاپ روشن باشه و برنامه در حال اجرا باشه.
با سرور ابری، بات **24 ساعته 7 روز هفته** روشن می‌مونه — حتی وقتی لپ‌تاپ خاموشه.

## گزینه ۱: Render.com (رایگان - پیشنهادی)

### مراحل:

1. **ثبت‌نام در Render:**
   - برو به https://render.com
   - با GitHub ثبت‌نام کن

2. **آپلود کد به GitHub:**
   - یه Repository جدید توی GitHub بساز (مثلاً `crypto-signal-bot`)
   - فایل‌های پوشه `crypto-signal-bot` رو آپلود کن
   - **مهم:** فایل `config.py` رو آپلود نکن (توステ‌های محیطی تنظیم می‌کنیم)

3. **ساخت Web Service:**
   - توی Render روی `New +` بزن
   - `Web Service` رو انتخاب کن
   - Repository خودت رو انتخاب کن
   - تنظیمات:
     - **Name:** `crypto-signal-bot`
     - **Runtime:** `Python 3`
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `python wsgi.py`
     - **Plan:** `Free`

4. **تنظیم Environment Variables:**
   - توی بخش `Environment` این متغیرها رو اضافه کن:
     - `TELEGRAM_BOT_TOKEN` = `8763890105:AAGbAQgr75k_kIGU7qgKrdNNo9aPFcqqtC8`
     - `TELEGRAM_CHAT_ID` = `7769330487`

5. **Deploy:**
   - روی `Create Web Service` بزن
   - صبر کن تا build تموم بشه
   - بات خودکار شروع می‌کنه به کار

### مزایا:
- ✅ رایگان (750 ساعت در ماه)
- ✅ خودکار ری‌استارت می‌شه اگه کرش کنه
- ✅ 24/7 روشنه
- ✅ با گوشی هم می‌تونی وضعیت رو چک کنی

### معایب:
- ❌ توی پلن رایگان، بعد از 15 دقیقه عدم فعالیت اسلیپ می‌شه
- ❌ برای حل این مشکل، یه pingReader از UptimeRobot بذار (پایین رو بخون)

---

## گزینه ۲: Railway.app (رایگان - ساده‌تر)

### مراحل:

1. برو به https://railway.app
2. با GitHub وارد شو
3. `New Project` → `Deploy from GitHub repo`
4. Repository رو انتخاب کن
5. تنظیمات:
   - Railway خودکار `requirements.txt` رو می‌خونه
   - `Start Command:` `python wsgi.py`
6. Environment Variables:
   - `TELEGRAM_BOT_TOKEN` = توکن بات
   - `TELEGRAM_CHAT_ID` = `7769330487`
7. Deploy بزن

### مزایا:
- ✅ رایگان ($5 اعتبار ماهانه)
- ✅ بسیار ساده
- ✅ لاگ‌های زنده

---

## گزینه ۳: PythonAnywhere (رایگان)

### مراحل:

1. برو به https://www.pythonanywhere.com
2. ثبت‌نام کن (account رایگان)
3. تب `Files` رو باز کن
4. یه پوشه `crypto-signal-bot` بساز و فایل‌ها رو آپلود کن
5. تب `Tasks` رو باز کن
6. یه task جدید بساز:
   - Command: `python3 /home/USERNAME/crypto-signal-bot/wsgi.py`
   - Recurrence: `Every hour`
7. Environment variables رو توی فایل config.py مستقیم تنظیم کن

### مزایا:
- ✅ رایگان
- ✅ داری Task Scheduler داخلی

### معایب:
- ❌ WebSocket ممکنه توی پلن رایگان محدود باشه
- ❌ هر 3 ماه باید تمدید کنی

---

## جلوگیری از sleep توی Render رایگان (UptimeRobot)

توی پلن رایگان Render، بعد از 15 دقیقه بدون ترافیک، سرور می‌خوابه.
برای حل این مشکل:

1. برو به https://uptimerobot.com
2. ثبت‌نام کن (رایگان)
3. `Add New Monitor` بزن:
   - Monitor Type: `HTTP(s)`
   - URL: آدرس Render باتت (مثلاً `https://crypto-signal-bot.onrender.com`)
   - Monitoring Interval: `5 minutes`
4. ذخیره کن

این کاری می‌کنه بات هر 5 دقیقه یه درخواست بگیره و خوابه نشه.

---

## تنظیمات config.py برای سرور

توی سرور، به جای اینکه `config.py` رو آپلود کنی، متغیرهای محیطی استفاده کن:

توی فایل `config.py` این تغییر رو بده:

```python
import os

# از متغیرهای محیطی استفاده کن اگه موجود باشن
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8763890105:AAGbAQgr75k_kIGU7qgKrdNNo9aPFcqqtC8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # به صورت رشته تنظیم کن
```

اگه از متغیر محیطی استفاده کنی، یعنی توی داشبورد Render این مقادیر رو تنظیم کنی،
دیگه نیازی نیست توکن رو توی کد بذاری و امن‌تره.

---

## خلاصه مراحل:

1. ✅ کد رو توی GitHub بذار
2. ✅ توی Render یا Railway ثبت‌نام کن
3. ✅ Repository رو وصل کن
4. ✅ Environment variables رو تنظیم کن (token + chat_id)
5. ✅ Deploy بزن
6. ✅ UptimeBot رو تنظیم کن (برای جلوگیری از sleep)
7. ✅ تمام! بات 24/7 روشنه

بعد از این، با گوشی فقط تلگرام رو باز کن و `/scan` یا `/status` بزن.
