import streamlit as st
import feedparser
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import re
from html import unescape
from collections import Counter

st.set_page_config(page_title="MK Daily English", page_icon="📰", layout="centered")

st.title("📰 MK Daily English")
st.caption("매일경제 TOP 5 · 기사당 핵심 영어 문장 1개 + 구조 분석")

RSS_URL = "https://www.mk.co.kr/rss/30000001/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
}

# These terms help remove photo/caption/advertising material from the article text.
NOISE_WORDS = [
    "포토", "사진", "이미지", "영상", "사진= ", "사진=", "그래픽",
    "Photo", "PHOTO", "Image", "image", "영상취재", "포토뉴스",
    "ⓒ", "Copyright", "무단전재", "배포 금지"
]

def clean(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def is_noise(text):
    t = text.strip()
    if len(t) < 25:
        return True
    if any(x in t for x in NOISE_WORDS):
        return True
    # Typical photo captions / credit lines
    if re.match(r"^(사진|포토|이미지|그래픽|자료사진)\s*[:=]", t, re.I):
        return True
    return False

@st.cache_data(ttl=600)
def load_news():
    feed = feedparser.parse(RSS_URL)
    return [{
        "title": clean(entry.get("title", "제목 없음")),
        "summary": clean(entry.get("summary") or entry.get("description") or ""),
        "link": entry.get("link", ""),
        "published": entry.get("published", "")
    } for entry in feed.entries[:5]]

@st.cache_data(ttl=1800)
def get_article_paragraphs(url):
    if not url:
        return []
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "form", "figure", "figcaption"]):
            tag.decompose()

        selectors = [
            "div.article_body", "div.news_cnt_detail_wrap",
            "div.article_txt", "div#article_body", "article"
        ]

        paragraphs = []
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                paragraphs = [clean(p.get_text(" ", strip=True))
                              for p in node.find_all(["p", "div"])]
                paragraphs = [p for p in paragraphs if not is_noise(p)]
                if paragraphs:
                    break

        if not paragraphs:
            paragraphs = [clean(p.get_text(" ", strip=True))
                          for p in soup.find_all("p")]
            paragraphs = [p for p in paragraphs if not is_noise(p)]

        result, seen = [], set()
        for p in paragraphs:
            # Remove obvious duplicate UI/metadata lines
            if p not in seen and len(p) >= 30:
                seen.add(p)
                result.append(p)
        return result
    except Exception:
        return []

def split_sentences(text):
    # Korean sentence boundaries plus English punctuation
    parts = re.split(r'(?<=[.!?。！？])\s+|(?<=[다요죠음함임됨])\s+', text)
    return [p.strip() for p in parts if len(p.strip()) >= 30 and not is_noise(p)]

def sentence_score(sentence, all_text, index):
    words = re.findall(r"[가-힣A-Za-z]{2,}", sentence.lower())
    freq = Counter(re.findall(r"[가-힣A-Za-z]{2,}", all_text.lower()))

    stop = {
        "그리고","그러나","이번","관련","대해","있는","있다","했다","하는",
        "것으로","대한","통해","위해","따라","에서","으로","이라고","했다며",
        "밝혔다","전했다","있는","것","수","등","및","또한","the","and","for",
        "with","that","this","from","have","has","were","will","into","about"
    }
    score = sum(freq[w] for w in words if w not in stop)

    # News leads are useful, but don't let the first sentence dominate.
    score += max(0, 8 - index) * 1.2

    # Prefer substantive sentences and penalize captions/quotes that are too short.
    if 50 <= len(sentence) <= 350:
        score += 10
    elif len(sentence) > 500:
        score -= 4
    if sentence.startswith(("연합뉴스", "정부", "업계")):
        score += 1
    return score

@st.cache_data(ttl=3600)
def make_english_summary(paragraphs, fallback):
    source = " ".join(paragraphs) if paragraphs else fallback
    sentences = split_sentences(source)

    if not sentences:
        return ""

    # Pick exactly ONE useful and slightly challenging sentence from the article.
    # Prefer sentences containing structures that are valuable for English study.
    scored = []
    teachable_patterns = [
        r"\\bwhich\\b", r"\\bthat\\b", r"\\bwhile\\b",
        r"\\bbecause\\b", r"\\balthough\\b", r"\\bdespite\\b",
        r"\\baccording to\\b", r"\\bby\\b", r"\\bto\\s+\\w+",
        r"\\b(has|have|had)\\b.*\\b(been|\\w+ed)\\b"
    ]

    for i, s in enumerate(sentences):
        if is_noise(s) or len(s) < 50:
            continue

        score = 0
        score += min(len(s) / 80, 4)  # Prefer sentences with enough substance.
        score += max(0, 5 - i) * 0.6  # Leads are often important.
        score += sum(bool(re.search(p, s, re.I)) for p in teachable_patterns) * 3

        # Avoid sentences that are mostly numbers, names, or very short headlines.
        alpha = len(re.findall(r"[가-힣]", s))
        digits = len(re.findall(r"\\d", s))
        if digits > alpha:
            score -= 2

        scored.append((score, s))

    if not scored:
        scored = [(1, sentences[0])]

    korean_sentence = max(scored, key=lambda x: x[0])[1]

    try:
        return GoogleTranslator(source="ko", target="en").translate(korean_sentence).strip()
    except Exception:
        return ""


@st.cache_data(ttl=3600)
def translate_to_korean(text):
    if not text:
        return ""
    try:
        return GoogleTranslator(source="en", target="ko").translate(text)
    except Exception:
        return ""

def explain_structure(sentence):
    s = sentence.strip()
    explanations = []

    # Base pattern
    if re.search(r"\b(has|have|had)\s+been\s+\w+ed\b", s, re.I):
        explanations.append("**has/have been + p.p.** → 현재완료 수동태. 과거부터 현재까지 이어진 사실이나 결과를 나타냅니다.")
    elif re.search(r"\b(was|were|is|are|be)\s+\w+ed\b", s, re.I):
        explanations.append("**be + p.p.** → 수동태. 행동을 한 사람보다 행동을 받은 대상에 초점을 둡니다.")

    if re.search(r"\bwhich\b", s, re.I):
        explanations.append("**which + 동사 ...** → 앞의 명사나 앞 문장 내용을 설명하는 관계대명사절입니다.")
    if re.search(r"\bthat\b", s, re.I):
        explanations.append("**that + 주어 + 동사** → 앞의 동사/명사가 말하는 내용을 이어 주는 명사절 또는 관계절로 쓰였습니다.")
    if re.search(r"\bwhile\b", s, re.I):
        explanations.append("**while + 주어 + 동사** → '~하는 동안' 또는 두 상황을 대조하는 절을 연결합니다.")
    if re.search(r"\balthough\b", s, re.I):
        explanations.append("**although + 주어 + 동사** → '~이지만'이라는 양보절을 만듭니다.")
    if re.search(r"\bdespite\b", s, re.I):
        explanations.append("**despite + 명사/동명사** → '~에도 불구하고'라는 뜻입니다.")
    if re.search(r"\bbecause\b", s, re.I):
        explanations.append("**because + 주어 + 동사** → 원인이나 이유를 설명합니다.")
    if re.search(r"\baccording to\b", s, re.I):
        explanations.append("**according to + 명사** → '~에 따르면'이라는 출처를 나타냅니다.")
    if re.search(r"\bto\s+\w+\b", s, re.I):
        explanations.append("**to + 동사원형** → 목적이나 앞으로 할 행동을 나타내는 to부정사로 쓰일 수 있습니다.")

    if not explanations:
        explanations.append("기본 구조는 **주어(S) + 동사(V) + 목적어/보어(O/C)** 순서로 읽으면 됩니다. 긴 수식어는 먼저 괄호처럼 묶어 읽으면 이해하기 쉽습니다.")

    return explanations

news = load_news()

if not news:
    st.error("매일경제 뉴스를 가져오지 못했습니다.")
    st.stop()

st.success("매일경제 일반 뉴스 최신 TOP 5")

for i, item in enumerate(news, 1):
    st.markdown(f"## 🏆 TOP {i}")
    st.markdown(f"### {item['title']}")

    if item["published"]:
        st.caption(item["published"])

    if item["link"]:
        st.link_button("🇰🇷 매일경제 원문 보기", item["link"])

    paragraphs = get_article_paragraphs(item["link"])
    english_summary = make_english_summary(paragraphs, item["summary"])

    st.markdown("#### 🇺🇸 오늘의 핵심 영어 문장")

    if english_summary:
        st.markdown(f"**{english_summary}**")

        korean = translate_to_korean(english_summary)
        if korean:
            st.markdown(f"**뜻:** {korean}")

        st.markdown("#### 📚 문장 구조 분석")
        for explanation in explain_structure(english_summary):
            st.markdown(f"- {explanation}")

        st.markdown("**읽는 방법:**")
        chunks = re.split(
            r"\s+(?=(?:which|that|while|because|although|despite|according to|to)\b)",
            english_summary,
            flags=re.I
        )
        if len(chunks) > 1:
            st.write(" → ".join(chunks))
        else:
            st.write("문장의 핵심 주어와 동사를 먼저 찾고, 나머지 수식어를 붙여 읽어보세요.")
    else:
        st.caption("이번 기사에서 학습할 영어 문장을 가져오지 못했습니다.")

    if i < len(news):
        st.divider()

st.divider()
st.caption("기사당 영어 문장 1개만 제공합니다 · OpenAI API 미사용 · 사진/포토 캡션 등 비본문 자료는 제외합니다.")
