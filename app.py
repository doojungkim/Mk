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
st.caption("매일경제 TOP 5 · 7-line English Summary")

RSS_URL = "https://www.mk.co.kr/rss/30000001/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

@st.cache_data(ttl=600)
def load_news():
    feed = feedparser.parse(RSS_URL)
    return [{
        "title": clean(entry.get("title", "제목 없음")),
        "summary": clean(entry.get("summary") or entry.get("description") or ""),
        "link": entry.get("link", ""),
        "published": entry.get("published", "")
    } for entry in feed.entries[:5]]

def clean(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

@st.cache_data(ttl=1800)
def get_article_text(url):
    if not url:
        return ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
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
                paragraphs = [p for p in paragraphs if len(p) >= 25]
                if paragraphs:
                    break

        if not paragraphs:
            paragraphs = [clean(p.get_text(" ", strip=True))
                          for p in soup.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) >= 25]

        result, seen = [], set()
        for p in paragraphs:
            if p not in seen:
                seen.add(p)
                result.append(p)

        return "\n".join(result)
    except Exception:
        return ""

def split_sentences(text):
    # Korean and English sentence boundaries
    parts = re.split(r'(?<=[.!?。！？])\s+|(?<=[다요죠음함임됨])\s+', text)
    return [p.strip() for p in parts if len(p.strip()) >= 20]

@st.cache_data(ttl=3600)
def make_english_summary(text):
    if not text:
        return ""

    sentences = split_sentences(text)
    if not sentences:
        return ""

    # Prefer the first/lead sentences, then select additional informative sentences.
    if len(sentences) <= 7:
        chosen = sentences
    else:
        words = re.findall(r"[가-힣A-Za-z]{2,}", text.lower())
        freq = Counter(words)
        stopwords = {
            "그리고","그러나","이번","관련","대해","있는","있다","했다",
            "하는","것으로","대한","통해","위해","따라","에서","으로",
            "이라고","했다며","밝혔다","전했다","the","and","for","with",
            "that","this","from","have","has","were","will","into","about"
        }

        scored = []
        for idx, sentence in enumerate(sentences):
            sw = re.findall(r"[가-힣A-Za-z]{2,}", sentence.lower())
            score = sum(freq[w] for w in sw if w not in stopwords)
            score += max(0, 10 - idx) * 0.6
            scored.append((score, idx, sentence))

        chosen = [x[2] for x in sorted(sorted(scored, reverse=True)[:7], key=lambda x: x[1])]

    korean = " ".join(chosen)

    try:
        english = GoogleTranslator(source="ko", target="en").translate(korean)
    except Exception:
        return ""

    # Try to make approximately 7 readable lines by splitting translated sentences.
    en_sentences = re.split(r'(?<=[.!?])\s+', english.strip())
    en_sentences = [s.strip() for s in en_sentences if s.strip()]

    if len(en_sentences) > 7:
        en_sentences = en_sentences[:7]

    return "\n\n".join(en_sentences)

@st.cache_data(ttl=3600)
def extract_keywords(english):
    words = re.findall(r"\b[A-Za-z][A-Za-z'-]{3,}\b", english or "")
    stop = {
        "this","that","with","from","have","has","been","were","will",
        "into","about","their","there","which","while","after","before",
        "more","than","also","they","them","said","over","under","such",
        "what","when","where","who","how","and","the","for","are","was",
        "but","not","its","his","her","our","you","your","these","those"
    }
    result = []
    for word in words:
        w = word.lower()
        if w not in stop and w not in result:
            result.append(w)
    return result[:5]

def word_meaning_and_example(word):
    try:
        meaning = GoogleTranslator(source="en", target="ko").translate(word)
        example_en = GoogleTranslator(
            source="ko", target="en"
        ).translate(f"'{word}'을 사용하는 간단한 영어 예문을 하나 만들어 주세요.")
        return meaning, example_en
    except Exception:
        return "", ""

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

    st.markdown("#### 🇺🇸 English Summary")

    article_text = get_article_text(item["link"])

    if article_text:
        english_summary = make_english_summary(article_text)
    else:
        english_summary = make_english_summary(item["summary"])

    if english_summary:
        st.write(english_summary)
    else:
        st.warning("이 기사의 영어 요약을 가져오지 못했습니다.")

    st.markdown("#### 🔑 Key Words")

    for word in extract_keywords(english_summary):
        meaning, example = word_meaning_and_example(word)
        st.markdown(f"**{word}** — {meaning}")
        if example:
            st.caption(f"Example: {example}")

    if i < len(news):
        st.divider()

st.divider()
st.caption("OpenAI API 미사용 · 매일경제 RSS와 기사 페이지의 공개 접근 가능 내용을 바탕으로 번역합니다.")
