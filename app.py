import streamlit as st
import feedparser
from openai import OpenAI

st.set_page_config(page_title="MK Daily English", page_icon="📰", layout="centered")

st.title("📰 MK Daily English")
st.caption("매일경제 TOP 5 · AI 영어 뉴스 요약")

RSS_URL = "https://www.mk.co.kr/rss/30000001/"
MODEL = "gpt-5.6"

@st.cache_data(ttl=600)
def load_news():
    feed = feedparser.parse(RSS_URL)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            "title": entry.get("title", "제목 없음"),
            "summary": entry.get("summary", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
        })
    return items

def summarize_with_ai(client, title, summary):
    prompt = f"""
You are an English tutor helping a Korean adult learn English through Korean news.

Korean title:
{title}

Korean summary:
{summary}

Return ONLY this format:

ENGLISH TITLE:
(one natural English headline)

EASY ENGLISH:
(3 to 5 short, clear sentences suitable for an intermediate English learner)

KEY VOCABULARY:
1. word/phrase — simple English meaning — Korean meaning
2. word/phrase — simple English meaning — Korean meaning
3. word/phrase — simple English meaning — Korean meaning
4. word/phrase — simple English meaning — Korean meaning
5. word/phrase — simple English meaning — Korean meaning

KOREAN KEY POINT:
(one short Korean sentence)

Use only facts contained in the supplied title and summary. Do not invent facts.
"""
    response = client.responses.create(model=MODEL, input=prompt)
    return response.output_text

news = load_news()

if not news:
    st.error("매일경제 RSS에서 뉴스를 가져오지 못했습니다.")
    st.stop()

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception:
    st.error("OpenAI API 키를 찾을 수 없습니다.")
    st.info("Manage app → Settings → Secrets에 OPENAI_API_KEY를 등록해 주세요.")
    st.stop()

st.success(f"최신 기사 {len(news)}개를 가져왔습니다.")

for i, item in enumerate(news, 1):
    st.markdown(f"## {i}. {item['title']}")
    if item["published"]:
        st.caption(item["published"])

    with st.spinner("AI가 영어 학습용으로 정리하고 있습니다..."):
        try:
            st.markdown(summarize_with_ai(client, item["title"], item["summary"]))
        except Exception as e:
            st.error("AI 요약에 실패했습니다.")
            st.caption(str(e))
            if item["summary"]:
                st.write(item["summary"])

    if item["link"]:
        st.link_button("📰 매일경제 원문 보기", item["link"])

    if i < len(news):
        st.divider()

st.divider()
st.caption("매일경제 RSS의 제목·요약을 바탕으로 AI가 영어 학습용 콘텐츠를 생성합니다.")
