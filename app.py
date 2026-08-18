import streamlit as st
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import re
from html import unescape

st.set_page_config(page_title="MK Daily English", page_icon="📰", layout="centered")

st.title("📰 MK Daily English")
st.caption("매일경제 인기뉴스 TOP 5 · 최근 2시간 조회수 기준 · 뉴스 종합")

RANKING_URL = "https://www.mk.co.kr/news/ranking"
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
    """Official MK Popular News page, default '뉴스 종합' tab, top 5."""
    try:
        r = requests.get(RANKING_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        items = []
        seen = set()

        # Official ranking page: default "뉴스 종합" tab.
        # The page currently renders ranked article links as:
        # 1 title, 2 title, ... 30 title.
        for a in soup.find_all("a", href=True):
            title = clean(a.get_text(" ", strip=True))
            m = re.match(r"^(\d+)\s+(.+)$", title)
            if not m:
                continue

            rank = int(m.group(1))
            if not 1 <= rank <= 5:
                continue

            article_title = m.group(2).strip()
            href = a.get("href", "").strip()
            if not article_title or not href:
                continue

            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://www.mk.co.kr" + href
            elif not href.startswith("http"):
                continue

            key = (rank, href)
            if key in seen:
                continue

            seen.add(key)
            items.append({
                "rank": rank,
                "title": article_title,
                "summary": "",
                "link": href,
                "published": ""
            })

        # Keep exactly ranks 1-5 in order.
        by_rank = {}
        for item in items:
            by_rank.setdefault(item["rank"], item)

        result = [by_rank[i] for i in range(1, 6) if i in by_rank]
        return result
    except Exception:
        return []

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
                # Prefer actual paragraph tags. If the site uses divs for body
                # text, fall back to direct text blocks.
                ps = node.find_all("p")
                if ps:
                    paragraphs = [clean(p.get_text(" ", strip=True)) for p in ps]
                else:
                    paragraphs = [clean(x.get_text(" ", strip=True))
                                  for x in node.find_all("div")]
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

@st.cache_data(ttl=3600)
def translate_article_to_english(paragraphs, fallback):
    """Translate about 10 substantive Korean sentences from the article."""
    source = " ".join(paragraphs) if paragraphs else fallback
    sentences = split_sentences(source)

    # Remove repeated/metadata-like sentences and keep the article's flow.
    selected = []
    seen = set()
    for s in sentences:
        s = clean(s)
        if is_noise(s):
            continue
        key = re.sub(r"\s+", " ", s)
        if key in seen:
            continue
        seen.add(key)

        # Skip very short fragments/headline-like material.
        if len(s) < 35:
            continue

        selected.append(s)
        if len(selected) >= 10:
            break

    translated = []
    for s in selected:
        try:
            en = GoogleTranslator(source="ko", target="en").translate(s).strip()
            if en:
                translated.append(en)
        except Exception:
            continue

    return translated


def choose_difficult_sentence(sentences):
    """Choose one teachable sentence from the translated 10 sentences."""
    if not sentences:
        return ""

    patterns = [
        r"\\bwhich\\b", r"\\bthat\\b", r"\\bwhile\\b",
        r"\\balthough\\b", r"\\bdespite\\b", r"\\bbecause\\b",
        r"\\baccording to\\b", r"\\bwhile\\b",
        r"\\b(has|have|had)\\b", r"\\b(be|is|are|was|were)\\b.*\\bby\\b",
        r"\\bto\\s+\\w+"
    ]

    scored = []
    for i, s in enumerate(sentences):
        score = min(len(s) / 45, 8)
        score += sum(bool(re.search(p, s, re.I)) for p in patterns) * 3
        # Slight preference for sentences in the middle of the article,
        # avoiding the very first headline-like sentence.
        if i == 0:
            score -= 1
        scored.append((score, s))

    return max(scored, key=lambda x: x[0])[1]


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

st.success("매일경제 인기뉴스 TOP 5를 가져왔습니다.")

for i, item in enumerate(news, 1):
    st.markdown(f"## 🏆 TOP {i}")
    st.markdown(f"### {item['title']}")

    if item["published"]:
        st.caption(item["published"])

    if item["link"]:
        st.link_button("🇰🇷 매일경제 원문 보기", item["link"])

    paragraphs = get_article_paragraphs(item["link"])
    english_sentences = translate_article_to_english(paragraphs, item["summary"])

    st.markdown("#### 🇺🇸 Article in English")

    if english_sentences:
        for n, sentence in enumerate(english_sentences, 1):
            st.markdown(f"**{n}.** {sentence}")

        learning = choose_difficult_sentence(english_sentences)

        if learning:
            st.markdown("#### 📚 One Sentence to Study")
            st.markdown(f"**{learning}**")

            st.markdown("**Structure Analysis**")
            for explanation in explain_structure(learning):
                st.markdown(f"- {explanation}")

            st.markdown("**How to read it:**")
            chunks = re.split(
                r"\\s+(?=(?:which|that|while|because|although|despite|according to|to)\\b)",
                learning,
                flags=re.I
            )
            if len(chunks) > 1:
                st.write(" → ".join(chunks))
            else:
                st.write("Find the main subject and verb first, then attach the modifiers.")

    else:
        st.caption("기사 본문을 가져오지 못했습니다.")

    if i < len(news):
        st.divider()

st.divider()
st.caption("기사 본문 약 10문장 영어 번역 · 그중 1문장만 구조 분석 · OpenAI API 미사용 · 사진/포토 캡션 제외")
