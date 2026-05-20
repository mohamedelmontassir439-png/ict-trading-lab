# 🧠 ICT Trading Lab — دليل الإعداد

## الإعداد في 5 خطوات

### 1. تثبيت Python
تأكد أن Python 3.11+ مثبت على جهازك:
```
py --version
```

### 2. تثبيت المكتبات
```bash
py -m pip install -r requirements.txt
```

### 3. إضافة مفتاح Gemini API
المُنسّق الحالي (`agents/orchestrator.py`) يستخدم **Google Gemini**. عيّن المفتاح كمتغير بيئة (مُفضّل) ولا تلصق مفاتيحاً في المستودع:

**PowerShell (جلسة حالية):**
```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

احصل على مفتاح من: https://aistudio.google.com/apikey

*(اختياري)* إن استخدمت نسخة Anthropic الاحتياطية في `agents/orchestrator_ANTHROPIC_BACKUP.py` فعيّن `ANTHROPIC_API_KEY`.

### 4. تشغيل النظام
```bash
py main.py
```

### 5. فتح Dashboard
افتح المتصفح على:
```
http://localhost:5000
```

---

## هيكل النظام

```
ict_trading_lab/
├── main.py               ← نقطة الانطلاق (شغّل هذا)
├── config.py             ← الإعدادات (عدّل هنا)
├── requirements.txt      ← المكتبات
├── agents/
│   ├── data_agent.py     ← يجلب بيانات Binance + yfinance
│   ├── ict_agent.py      ← تحليل ICT كامل
│   ├── risk_agent.py     ← إدارة المخاطر
│   ├── executor_agent.py ← تنفيذ/إغلاق الصفقات
│   ├── orchestrator.py   ← Gemini يقرر الدخول
│   └── journal_agent.py  ← إحصائيات وتقارير
├── database/
│   └── models.py         ← SQLite قاعدة بيانات
├── dashboard/
│   └── app.py            ← واجهة ويب Flask
└── logs/
    └── trading.log       ← سجل كامل
```

---

## كيف يعمل النظام

```
كل 15 دقيقة:
  ├── هل نحن في Kill Zone? (London/NY/Asia)
  │     لا → انتظر
  │     نعم ↓
  ├── [Data Agent]        جلب بيانات حقيقية
  ├── [ICT Agent]         تحليل: Bias + OB + FVG + Liquidity
  ├── [Risk Agent]        حساب Entry/SL/TP + حجم الصفقة
  ├── [AI Orchestrator]   Gemini يقرر: ENTER أو SKIP
  └── [Executor Agent]    تنفيذ الصفقة الورقية
```

---

## مفاهيم ICT المطبقة

- ✅ Market Structure (BOS / CHoCH)
- ✅ Order Blocks (Bull & Bear)
- ✅ Fair Value Gaps (FVG)
- ✅ Liquidity Levels (BSL / SSL)
- ✅ Premium & Discount Zones
- ✅ Kill Zones (London / New York / Asian)
- ✅ Risk Management (1% per trade, 1:3 RR)
- ✅ Daily Loss Limit (3% max)

---

## إيقاف النظام

```
Ctrl + C
```

البيانات تُحفظ تلقائياً في `database/trading_lab.db`

---

## ملاحظة مهمة

هذا نظام **Paper Trading** (تداول ورقي).
لا يُستخدم مال حقيقي. الهدف: إثبات الجدارة خلال 3 أشهر.
