# مستشار الدولة — State Counselor

مساعد قانوني ذكي متخصص في التشريعات والقوانين الكويتية، مبني على Claude API.

## المتطلبات
- Python 3.9+
- مفتاح Anthropic API (احصل عليه من https://console.anthropic.com)

## التثبيت والتشغيل

```bash
# 1. ثبّت المكتبات
pip install -r requirements.txt

# 2. (اختياري) عيّن مفتاح API كمتغير بيئي
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# 3. شغّل السيرفر
python app.py
```

ثم افتح المتصفح على: http://localhost:5000

## إضافة/تحديث ملف القوانين

```bash
# ضع ملف PDF الجديد في مجلد data/
python process_pdf.py data/your_file.pdf
```

## النشر على الإنترنت

### Render.com (مجاني)
1. ارفع المشروع على GitHub
2. اربطه بـ Render.com
3. عيّن ANTHROPIC_API_KEY في Environment Variables

### Railway.app
1. ارفع المشروع على GitHub
2. اربطه بـ Railway
3. عيّن المتغيرات البيئية

## التقنيات المستخدمة
- **Backend**: Flask + Python
- **AI**: Claude API (Anthropic)
- **Search**: BM25-based text search
- **PDF Processing**: PyMuPDF
- **Frontend**: HTML/CSS/JS (RTL Arabic)

## ملاحظة مهمة
هذا المساعد للاسترشاد فقط ولا يُغني عن الاستشارة القانونية المتخصصة.
التشريعات محدثة حتى 4/11/2025 — إعداد المستشار جزاء العتيبي - وكيل محكمة الاستئناف.
