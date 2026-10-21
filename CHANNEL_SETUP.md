# راهنمای تنظیم کانال تلگرام برای بات

## مرحله ۱: ادمین کردن بات

1. توی کانال JASHUVA → Manage Channel → Administrators
2. "jashbot" رو پیدا کن
3. اگه هست → Edit → تیک **Post Messages** رو بزن
4. اگه نیست → Add Admin → سرچ کن: `@jashsignalbot`
5. تیک **Post Messages** رو بزن → Save

**مهم:** بات باید ادمین باشه وگره پیام نمی‌فرسته!

## مرحله ۲: پیدا کردن Channel ID

### روش ۱: ساده
1. برو توی مرورگر:
```
https://api.telegram.org/bot8763890105:AAGbAQgr75k_kIGU7qgKrdNNo9aPFcqqtC8/getUpdates
```
2. یه پیام توی کانال بفرست (مثلاً "test")
3. صفحه رو Refresh کن (F5)
4. توی JSON دنبال `"chat":{"id":-100xxxxxxx` بگرد
5. عدد `-100...` رو کپی کن

### روش ۲: از BotFather
1. برو توی @userinfobot
2. Forward یه پیام از کانالت
3. بات Channel ID رو می‌ده

### روش ۳: از Web
1. برو https://web.telegram.org
2. کانال رو باز کن
3. توی URL می‌بینی: `/c/1234567890`
4. Channel ID: `-1001234567890`

## مرحله ۳: تنظیم روی سرور

### روش ساده: به من بگو
Channel ID رو بهم بده (مثلاً `-1001234567890`) تا مستقیم توی کد بذارم.

### روش حرفه‌ای: Render
1. برو https://dashboard.render.com
2. سرویس `crypto-signal-bot` رو باز کن
3. برو توی Environment
4. Add Variable:
   - Key: `TELEGRAM_CHANNEL_ID`
   - Value: `-1001234567890` (همونی که پیدا کردی)
5. Save → Deploy

## مرحله ۴: تست

1. `/scan` بزن توی چت خصوصی
2. اگه همه چی درست باشه → سیگنال هم توی کانال میاد
3. اگه نیومد → چک کن jashbot ادمین هست یا نه

## ❌ خطاهای رایج

| خطا | دلیل | راه‌حل |
|-----|------|--------|
| `has no access to messages` | بات ادمین نیست | ادمین کن + Post Messages |
| `chat not found` | Channel ID اشتباهه | دوباره پیدا کن |
| `not enough rights` | دسترسی نداره | Edit admin → همه تیک‌ها رو بزن |
