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
st.caption("매일경제 TOP 5 · 원문 + 영어 요약")

RSS_URL = "https://www.mk.co.kr/rss/30000001/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

@st.cache_data(ttl=600)
def load_news():
    feed = feedparser.parse(RSS_URL)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            "title": clean_html(entry.get("title", "제목 없음")),
            "summary": clean_html(entry.get("summary") or entry.get("description") or ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", "")
        })
    return items

def clean_html(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

@st.cache_data(ttl=1800)
def get_article_text(url):
    if not url:
        return ""

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Remove non-article elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        selectors = [
            "div.article_body",
            "div.news_cnt_detail_wrap",
            "div.article_txt",
            "div#article_body",
            "article"
        ]

        paragraphs = []
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                paragraphs = [
                    clean_html(p.get_text(" ", strip=True))
                    for p in node.find_all(["p", "div"])
                ]
                paragraphs = [p for p in paragraphs if len(p) >= 30]
                if paragraphs:
                    break

        if not paragraphs:
            paragraphs = [
                clean_html(p.get_text(" ", strip=True))
                for p in soup.find_all("p")
            ]
            paragraphs = [p for p in paragraphs if len(p) >= 30]

        # Remove duplicates while preserving order
        result = []
        seen = set()
        for p in paragraphs:
            if p not in seen:
                seen.add(p)
                result.append(p)

        return "\n".join(result)

    except Exception:
        return ""

def split_sentences(text):
    # Korean/English sentence splitting
    parts = re.split(r'(?<=[.!?。！？])\s+|(?<=[다요죠음함임됨])\s+', text)
    return [p.strip() for p in parts if len(p.strip()) >= 25]

def extractive_summary(text, max_sentences=5):
    sentences = split_sentences(text)
    if len(sentences) <= max_sentences:
        return sentences

    # Very lightweight extractive ranking without an AI API.
    words = re.findall(r"[가-힣A-Za-z]{2,}", text.lower())
    freq = Counter(words)

    stopwords = {
        "그리고","그러나","때문","이번","관련","대해","있는","있다","했다",
        "하는","것으로","대한","통해","위해","따라","에서","으로","이라고",
        "했다며","밝혔다","전했다","the","and","for","with","that","this",
        "from","have","has","were","will","into","about"
    }

    scores = []
    for idx, sentence in enumerate(sentences):
        sw = re.findall(r"[가-힣A-Za-z]{2,}", sentence.lower())
        score = sum(freq[w] for w in sw if w not in stopwords)
        # Slight preference for early sentences because news articles often lead with the core event.
        score += max(0, 8 - idx) * 0.5
        scores.append((score, idx, sentence))

    chosen = sorted(scores, reverse=True)[:max_sentences]
    chosen = sorted(chosen, key=lambda x: x[1])
    return [x[2] for x in chosen]

@st.cache_data(ttl=3600)
def translate(text):
    if not text:
        return ""
    try:
        return GoogleTranslator(source="ko", target="en").translate(text)
    except Exception:
        return ""

news = load_news()

if not news:
    st.error("매일경제 뉴스를 가져오지 못했습니다.")
    st.stop()

st.success("매일경제 일반 뉴스 최신 TOP 5")

st.info(
    "한국어는 매일경제 원문으로 이동하고, 영어는 공개적으로 접근 가능한 원문 내용을 "
    "자동으로 추려 영어로 번역합니다. OpenAI API는 사용하지 않습니다."
)

for i, item in enumerate(news, 1):
    st.markdown(f"## 🏆 TOP {i}")
    st.markdown(f"### {item['title']}")

    if item["published"]:
        st.caption(item["published"])

    # Korean: link to original article
    if item["link"]:
        st.link_button("🇰🇷 매일경제 원문 보기", item["link"])

    st.markdown("#### 🇺🇸 English Summary")

    article_text = get_article_text(item["link"])

    if article_text:
        summary_sentences = extractive_summary(article_text, 5)
        summary_ko = " ".join(summary_sentences)
        summary_en = translate(summary_ko)

        if summary_en:
            st.write(summary_en)
        else:
            st.warning("영어 번역을 가져오지 못했습니다.")
    else:
        # Fall back to RSS summary if the article page cannot be accessed.
        if item["summary"]:
            st.write(translate(item["summary"]))
            st.caption("원문 페이지에 직접 접근할 수 없어 RSS 요약을 사용했습니다.")
        else:
            st.warning("이 기사의 내용을 가져오지 못했습니다.")

    # Vocabulary from the English summary
    st.markdown("#### 🔑 Key Words")
    english_for_words = summary_en if article_text and summary_en else translate(item["summary"])
    words = re.findall(r"\b[A-Za-z][A-Za-z'-]{3,}\b", english_for_words or "")
    stop = {
        "this","that","with","from","have","has","been","were","will",
        "into","about","their","there","which","while","after","before",
        "more","than","also","they","them","said","over","under","such",
        "what","when","where","who","how","and","the","for","are","was",
        "but","not","its","his","her","our","you","your"
    }
    seen = []
    for word in words:
        w = word.lower()
        if w not in stop and w not in seen:
            seen.append(w)
    for word in seen[:5]:
        st.markdown(f"- **{word}**")

    if i < len(news):
        st.divider()

st.divider()
st.caption("출처: 매일경제 RSS 및 각 기사 원문 · OpenAI API 미사용")
