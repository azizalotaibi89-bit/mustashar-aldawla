"""
مستشار الدولة - State Counselor
A ChatGPT-like interface for querying Kuwaiti legislation
Powered by Claude API + Smart Text Search
"""
import os
import json
import re
import math
from collections import Counter
from flask import Flask, render_template, request, jsonify, Response
import anthropic

app = Flask(__name__)

# ============================================================
# Configuration
# ============================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
MAX_CONTEXT_CHUNKS = 15
CHUNKS_FILE = os.path.join(os.path.dirname(__file__), "data", "chunks.json")

# ============================================================
# Load and index chunks at startup
# ============================================================
print("📚 Loading legislation chunks...")
with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    CHUNKS = json.load(f)
print(f"✅ Loaded {len(CHUNKS)} chunks")

# Build TF-IDF index for better search
def tokenize(text):
    """Simple Arabic-aware tokenizer."""
    # Remove diacritics
    text = re.sub(r'[\u0610-\u061A\u064B-\u065F\u0670]', '', text)
    # Split on non-Arabic, non-digit characters
    tokens = re.findall(r'[\u0600-\u06FF\u0750-\u077F]+|\d+', text)
    # Remove very short tokens
    return [t for t in tokens if len(t) > 1]

# Build document frequency
print("🔍 Building search index...")
doc_freq = Counter()
chunk_tokens = []
for chunk in CHUNKS:
    tokens = set(tokenize(chunk["text"]))
    chunk_tokens.append(tokens)
    for token in tokens:
        doc_freq[token] += 1

N = len(CHUNKS)
print(f"✅ Search index ready ({len(doc_freq)} unique terms)")

def search_chunks(query, top_k=MAX_CONTEXT_CHUNKS):
    """Search for the most relevant chunks using BM25-like scoring."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return CHUNKS[:top_k]

    scores = []
    k1 = 1.5
    b = 0.75
    avg_dl = sum(len(ct) for ct in chunk_tokens) / max(N, 1)

    for i, chunk in enumerate(CHUNKS):
        score = 0
        dl = len(chunk_tokens[i])

        for token in query_tokens:
            if token not in chunk_tokens[i]:
                continue

            tf = chunk["text"].count(token)
            df = doc_freq.get(token, 1)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)

            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1)))
            score += idf * tf_norm

        # Boost exact phrase matches
        if query in chunk["text"]:
            score *= 2.0

        # Boost section title matches
        for token in query_tokens:
            if token in chunk.get("section", ""):
                score *= 1.3

        if score > 0:
            scores.append((score, i))

    scores.sort(reverse=True)
    results = []
    for score, idx in scores[:top_k]:
        result = CHUNKS[idx].copy()
        result["score"] = score
        results.append(result)

    return results

# ============================================================
# Routes
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    """Check if server has an API key configured."""
    has_key = bool(ANTHROPIC_API_KEY)
    return jsonify({"has_server_key": has_key})

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_message:
        return jsonify({"error": "الرجاء إدخال سؤال"}), 400

    api_key = data.get("api_key", "") or ANTHROPIC_API_KEY
    if not api_key:
        return jsonify({"error": "الرجاء إدخال مفتاح API"}), 400

    # Search for relevant chunks
    relevant_chunks = search_chunks(user_message)

    # Build context from relevant chunks
    context_parts = []
    for chunk in relevant_chunks:
        section_info = f" [{chunk['section']}]" if chunk.get("section") else ""
        context_parts.append(f"--- صفحة {chunk['page']}{section_info} ---\n{chunk['text']}")

    context = "\n\n".join(context_parts)

    # Build the system prompt
    system_prompt = """أنت "مستشار الدولة" — مساعد قانوني ذكي متخصص في التشريعات والقوانين الكويتية.

## مهمتك:
- الإجابة على الأسئلة القانونية بناءً على النصوص التشريعية المتاحة لك فقط
- الرد بأسلوب بشري واضح ومفهوم، كأنك محامي خبير يشرح للعميل
- ذكر رقم المادة والقانون المرتبط عند الإجابة
- إذا لم تجد إجابة في النصوص المتاحة، قل ذلك بوضوح

## قواعد الرد:
1. ابدأ بالإجابة المباشرة على السؤال
2. اذكر النص القانوني ذا الصلة (رقم المادة والقانون)
3. اشرح المادة بلغة بسيطة ومفهومة
4. إذا كان هناك تعديلات أو استثناءات، اذكرها
5. في النهاية، نبّه أن هذا للاسترشاد فقط وليس استشارة قانونية رسمية

## أسلوب الرد:
- تحدث بالعربية الفصحى البسيطة
- كن ودوداً ومهنياً
- لا تستخدم مصطلحات معقدة بدون شرحها
- إذا كان السؤال عاماً، اطلب توضيحاً

## تنبيه مهم:
هذه النصوص التشريعية محدثة حتى 4/11/2025 من إعداد المستشار جزاء العتيبي - وكيل محكمة الاستئناف."""

    # Build messages
    messages = []

    # Add conversation history (last 6 exchanges max)
    for msg in history[-12:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message with context
    user_content = f"""السؤال: {user_message}

--- النصوص القانونية ذات الصلة ---
{context}
--- نهاية النصوص ---

أجب على السؤال بناءً على النصوص القانونية أعلاه. إذا لم تجد إجابة واضحة في النصوص، قل ذلك."""

    messages.append({"role": "user", "content": user_content})

    # Call Claude API with streaming
    try:
        client = anthropic.Anthropic(api_key=api_key)

        def generate():
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=messages
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return Response(generate(), mimetype="text/event-stream")

    except anthropic.AuthenticationError:
        return jsonify({"error": "مفتاح API غير صحيح. الرجاء التحقق من المفتاح."}), 401
    except anthropic.RateLimitError:
        return jsonify({"error": "تم تجاوز حد الاستخدام. الرجاء المحاولة لاحقاً."}), 429
    except Exception as e:
        return jsonify({"error": f"حدث خطأ: {str(e)}"}), 500

@app.route("/api/search", methods=["POST"])
def search():
    """Direct search endpoint for quick lookups."""
    data = request.json
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"results": []})

    results = search_chunks(query, top_k=10)
    return jsonify({"results": results})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
