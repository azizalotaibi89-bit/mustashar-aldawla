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
MAX_CONTEXT_CHUNKS = 25
CHUNKS_FILE = os.path.join(os.path.dirname(__file__), "data", "chunks.json")

# ============================================================
# Load and index chunks at startup
# ============================================================
print("📚 Loading legislation chunks...")
with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    CHUNKS = json.load(f)
print(f"✅ Loaded {len(CHUNKS)} chunks")

# Build TF-IDF index for better search
def normalize_arabic(text):
    """Normalize Arabic text for better matching."""
    # Remove diacritics
    text = re.sub(r'[\u0610-\u061A\u064B-\u065F\u0670]', '', text)
    # Normalize alef variants to bare alef
    text = re.sub(r'[إأآا]', 'ا', text)
    # Normalize taa marbuta to haa
    text = text.replace('ة', 'ه')
    # Normalize alef maksura to yaa
    text = text.replace('ى', 'ي')
    # Remove tatweel
    text = text.replace('\u0640', '')
    return text

def tokenize(text):
    """Arabic-aware tokenizer with normalization."""
    text = normalize_arabic(text)
    # Split on non-Arabic, non-digit characters
    tokens = re.findall(r'[\u0600-\u06FF\u0750-\u077F]+|\d+', text)
    # Keep even single-char tokens (important for Arabic)
    return tokens

# Build document frequency and normalized text cache
print("🔍 Building search index...")
doc_freq = Counter()
chunk_tokens = []
chunk_normalized = []  # Cache normalized text for substring matching
for chunk in CHUNKS:
    norm_text = normalize_arabic(chunk["text"])
    chunk_normalized.append(norm_text)
    tokens = set(tokenize(chunk["text"]))
    chunk_tokens.append(tokens)
    for token in tokens:
        doc_freq[token] += 1

N = len(CHUNKS)
print(f"✅ Search index ready ({len(doc_freq)} unique terms)")

def search_chunks(query, top_k=MAX_CONTEXT_CHUNKS):
    """Search for the most relevant chunks using BM25 + substring + neighbor boosting."""
    query_norm = normalize_arabic(query)
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
                # Try substring match in normalized text
                if len(token) > 2 and token in chunk_normalized[i]:
                    score += 0.5  # Partial credit for substring
                continue

            tf = chunk_normalized[i].count(token)
            df = doc_freq.get(token, 1)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)

            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1)))
            score += idf * tf_norm

        # Boost exact phrase matches (on normalized text)
        if query_norm in chunk_normalized[i]:
            score *= 3.0

        # Boost partial phrase matches (3+ word sequences)
        if len(query_tokens) >= 3:
            for j in range(len(query_tokens) - 2):
                trigram = ' '.join(query_tokens[j:j+3])
                if trigram in chunk_normalized[i]:
                    score *= 1.5

        # Boost section title matches
        if chunk.get("section"):
            section_norm = normalize_arabic(chunk["section"])
            for token in query_tokens:
                if token in section_norm:
                    score *= 1.3

        if score > 0:
            scores.append((score, i))

    # Add neighboring chunks for top results (context window)
    scores.sort(reverse=True)
    top_indices = set()
    neighbor_entries = []
    for score, idx in scores[:top_k]:
        top_indices.add(idx)

    for score, idx in scores[:min(10, len(scores))]:
        # Add previous and next chunks as neighbors with reduced score
        for neighbor in [idx - 1, idx + 1]:
            if 0 <= neighbor < N and neighbor not in top_indices:
                top_indices.add(neighbor)
                neighbor_entries.append((score * 0.3, neighbor))

    all_scored = scores[:top_k] + neighbor_entries
    all_scored.sort(reverse=True)

    results = []
    seen = set()
    for score, idx in all_scored:
        if idx in seen:
            continue
        seen.add(idx)
        if len(results) >= top_k:
            break
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
    system_prompt = """أنت "مستشار الدولة" — محامي خبير متخصص في التشريعات والقوانين الكويتية. أنت لست مجرد أداة بحث، بل مستشار قانوني حقيقي يقدم تحليلاً ورأياً قانونياً.

## مهمتك:
- الإجابة على الأسئلة القانونية بناءً على النصوص التشريعية المتاحة لك
- الرد بأسلوب بشري واضح ومفهوم، كأنك محامي خبير يشرح للعميل
- ذكر رقم المادة والقانون المرتبط عند الإجابة
- إذا لم تجد إجابة في النصوص المتاحة، قل ذلك بوضوح
- تقديم رأيك وتحليلك القانوني في كل إجابة

## قواعد الرد:
1. ابدأ بالإجابة المباشرة على السؤال
2. اذكر النص القانوني ذا الصلة (رقم المادة والقانون)
3. اشرح المادة بلغة بسيطة ومفهومة
4. إذا كان هناك تعديلات أو استثناءات، اذكرها
5. قدّم رأيك القانوني وتحليلك للموضوع — مثلاً: ما هو التفسير الأرجح، ما هي النقاط المهمة التي يجب الانتباه لها، وما هي النصيحة القانونية العملية

## ممنوع تماماً:
- لا تضف أي تنبيه أو تحذير في نهاية الإجابة
- لا تقل "هذا للاسترشاد فقط" أو "استشر محامي" أو "لا تعتمد على هذا" أو أي عبارة مشابهة
- لا تقل "أنا مجرد مساعد" أو "أنا لست محامي" أو "هذه ليست استشارة قانونية رسمية"
- لا تضف أي إخلاء مسؤولية من أي نوع
- أجب بثقة كاملة كأنك محامي خبير يقدم استشارة حقيقية

## أسلوب الرد:
- تحدث بالعربية الفصحى البسيطة
- كن ودوداً ومهنياً وواثقاً
- لا تستخدم مصطلحات معقدة بدون شرحها
- إذا كان السؤال عاماً، اطلب توضيحاً
- أعطِ رأيك بجرأة ووضوح

## معلومة:
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

أجب على السؤال بناءً على النصوص القانونية أعلاه وقدّم رأيك وتحليلك القانوني. لا تضف أي تنبيه أو إخلاء مسؤولية."""

    messages.append({"role": "user", "content": user_content})

    # Call Claude API with streaming
    try:
        client = anthropic.Anthropic(api_key=api_key)

        def generate():
            try:
                with client.messages.stream(
                    model=MODEL,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages
                ) as stream:
                    for text in stream.text_stream:
                        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
            except anthropic.AuthenticationError:
                yield f"data: {json.dumps({'error': 'مفتاح API غير صحيح'}, ensure_ascii=False)}\n\n"
            except anthropic.RateLimitError:
                yield f"data: {json.dumps({'error': 'تم تجاوز حد الاستخدام. حاول لاحقاً'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': f'حدث خطأ: {str(e)}'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return Response(generate(), mimetype="text/event-stream",
                       headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

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
