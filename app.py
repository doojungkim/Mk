import streamlit as st
import feedparser
from deep_translator import GoogleTranslator
import re

st.set_page_config(
    page_title="MK Daily English",
    page_icon="📰",
    layout="centered"
)

st.title("📰 MK Daily English")
st.caption("매일경제 TOP 5 · 영어 번역 + 핵심 단어")

RSS_URL = "https://www.mk.co.kr/rss/30000001/"

@st.cache_data(ttl=600)
def load_news():
    feed = feedparser.parse(RSS_URL)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            "title": entry.get("title", "제목 없음"),
            "summary": entry.get("summary", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", "")
        })
    return items

@st.cache_data(ttl=3600)
def translate_text(text):
    if not text:
        return ""
    # Remove common HTML tags from RSS summaries.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    try:
        return GoogleTranslator(source="ko", target="en").translate(text)
    except Exception:
        return "영어 번역을 가져오지 못했습니다."

news = load_news()

if not news:
    st.error("매일경제 RSS에서 뉴스를 가져오지 못했습니다.")
    st.stop()

st.success(f"최신 기사 {len(news)}개를 가져왔습니다.")

st.info("💡 AI API 없이 번역 서비스를 이용합니다. 기사마다 '영어로 보기'를 누르면 번역됩니다.")

for i, item in enumerate(news, 1):
    st.markdown(f"## {i}. {item['title']}")

    if item["published"]:
        st.caption(item["published"])

    # Title translation
    with st.expander("🇺🇸 English"):
        english_title = translate_text(item["title"])
        st.markdown(f"### {english_title}")

        if item["summary"]:
            english_summary = translate_text(item["summary"])
            st.write(english_summary)

        st.markdown("### 🔑 Key Words")
        st.write("아래는 기사 제목에서 영어 학습에 유용한 핵심 단어를 뽑은 예시입니다.")

        # Simple title-based word hints; no AI/API needed.
        words = re.findall(r"[A-Za-z]{4,}", english_title)
        seen = []
        for w in words:
            wl = w.lower()
            if wl not in seen:
                seen.append(wl)

        if seen:
            for w in seen[:5]:
                st.markdown(f"- **{w}**")
        else:
            st.write("번역된 제목에서 핵심 단어를 자동으로 추출하지 못했습니다.")

    if item["link"]:
        st.link_button("📰 매일경제 원문 보기", item["link"])

    if i < len(news):
        st.divider()

st.divider()
st.caption("이 버전은 OpenAI API를 사용하지 않습니다. 번역은 GoogleTranslator를 통해 처리됩니다.")
