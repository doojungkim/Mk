import streamlit as st
import feedparser
from datetime import datetime

st.set_page_config(
    page_title="MK Daily English",
    page_icon="📰",
    layout="centered"
)

st.title("📰 MK Daily English")
st.caption("매일경제 RSS 기반 뉴스 TOP 5 · 1차 버전")

# 매일경제 RSS 공식 페이지에서 확인할 수 있는 RSS 주소를 기본값으로 둡니다.
# RSS 주소가 변경되면 아래 URL만 수정하면 됩니다.
RSS_URL = "https://www.mk.co.kr/rss/30000001/"

@st.cache_data(ttl=600)
def load_news():
    feed = feedparser.parse(RSS_URL)

    if getattr(feed, "bozo", False) and not feed.entries:
        return []

    items = []
    for entry in feed.entries[:5]:
        title = entry.get("title", "제목 없음")
        link = entry.get("link", "")
        summary = entry.get("summary", "")
        published = entry.get("published", "")
        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "published": published
        })
    return items

news = load_news()

if not news:
    st.error("뉴스를 가져오지 못했습니다. RSS 주소가 변경되었을 수 있습니다.")
    st.info("app.py의 RSS_URL을 매일경제의 현재 RSS 주소로 확인해 주세요.")
else:
    st.success(f"최신 기사 {len(news)}개를 가져왔습니다.")

    for i, item in enumerate(news, 1):
        st.subheader(f"{i}. {item['title']}")

        if item["published"]:
            st.caption(item["published"])

        if item["summary"]:
            st.write(item["summary"])

        if item["link"]:
            st.link_button("원문 보기", item["link"])

        if i < len(news):
            st.divider()

st.divider()
st.caption("1차 버전: RSS 뉴스 수집 및 모바일 웹 표시")
