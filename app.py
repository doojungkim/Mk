import streamlit as st
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import re
from html import unescape
from urllib.parse import urljoin

st.set_page_config(page_title="MK Daily English", page_icon="📰", layout="centered")

st.title("📰 MK Daily English")
st.caption("매일경제 뉴스 종합 TOP 5 + 국제 TOP 1 · 최근 2시간 조회수 기준")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
    )
}

# IMPORTANT:
# '뉴스 종합' is a separate ranking page on MK.
# The old app used /news/ranking/ and therefore could pick up other ranking lists.
NEWS_ALL_URL = "https://www.mk.co.kr/news/ranking/newsall"
WORLD_URL = "https://www.mk.co.kr/news/ranking/world"

NOISE_WORDS = [
    "포토", "사진", "이미지", "영상", "그래픽", "자료사진",
    "Photo", "PHOTO", "Image", "image", "영상취재",
    "ⓒ", "Copyright", "무단전재", "배포 금지"
]

def clean(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def is_noise(text):
    t = clean(text)
    if len(t) < 25:
        return True
    if any(x in t for x in NOISE_WORDS):
        return True
    if re.match(r"^(사진|포토|이미지|그래픽|자료사진)\s*[:=]", t, re.I):
        return True
    return False

def normalize_url(href):
    if not href:
        return ""
    href = href.strip()
    return urljoin("https://www.mk.co.kr", href)

@st.cache_data(ttl=300)
def fetch_ranking(url, label, count):
    """Fetch only the requested ranking page and return exact ranks 1..count."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        by_rank = {}

        # The ranking page contains article links such as:
        # 1 title, 2 title, ... 30 title.
        for a in soup.find_all("a", href=True):
            raw = clean(a.get_text(" ", strip=True))
            m = re.match(r"^(\d+)\s+(.+)$", raw)
            if not m:
                continue

            rank = int(m.group(1))
            if not 1 <= rank <= count:
                continue

            title = m.group(2).strip()
            link = normalize_url(a.get("href"))
            if not title or not link:
                continue

            # Exclude obvious non-article destinations.
            if "mk.co.kr/news/" not in link:
                continue

            # Prefer the first valid link for each rank.
            by_rank.setdefault(rank, {
                "rank": rank,
                "title": title,
                "link": link,
                "category": label,
            })

        return [by_rank[i] for i in range(1, count + 1) if i in by_rank]
    except Exception as e:
        return []

@st.cache_data(ttl=1800)
def load_news():
    news = fetch_ranking(NEWS_ALL_URL, "뉴스 종합", 5)
    world = fetch_ranking(WORLD_URL, "국제", 1)
    return news + world

@st.cache_data(ttl=1800)
def get_article_paragraphs(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Remove non-article material, especially photo/caption blocks.
        for tag in soup([
            "script", "style", "nav", "header", "footer", "aside",
            "form", "figure", "figcaption", "iframe", "video"
        ]):
            tag.decompose()

        selectors = [
            "div.article_body",
            "div.news_cnt_detail_wrap",
            "div.article_txt",
            "div#article_body",
            "article",
        ]

        paragraphs = []
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue

            ps = node.find_all("p")
            if ps:
                candidates = [clean(p.get_text(" ", strip=True)) for p in ps]
            else:
                candidates = [
                    clean(x.get_text(" ", strip=True))
                    for x in node.find_all(["div", "p"])
                ]

            candidates = [p for p in candidates if not is_noise(p)]
            if candidates:
                paragraphs = candidates
                break

        if not paragraphs:
            paragraphs = [
                clean(p.get_text(" ", strip=True))
                for p in soup.find_all("p")
                if not is_noise(p.get_text(" ", strip=True))
            ]

        result, seen = [], set()
        for p in paragraphs:
            if len(p) < 30:
                continue
            key = re.sub(r"\s+", " ", p)
            if key in seen:
                continue
            seen.add(key)
            result.append(p)

        return result
    except Exception:
        return []

def split_korean_sentences(text):
    text = clean(text)
    # Korean news sentences usually end with these endings or punctuation.
    parts = re.split(
        r"(?<=[.!?。！？])\s+|(?<=[다요죠음함임됨])\s+",
        text
    )
    return [p.strip() for p in parts if len(p.strip()) >= 30 and not is_noise(p)]

def select_source_sentences(paragraphs, max_sentences=10):
    selected, seen = [], set()

    for paragraph in paragraphs:
        for sentence in split_korean_sentences(paragraph):
            key = re.sub(r"\s+", " ", sentence)
            if key in seen:
                continue
            seen.add(key)

            # Avoid captions, headlines and very short fragments.
            if len(sentence) < 35 or is_noise(sentence):
                continue

            selected.append(sentence)
            if len(selected) >= max_sentences:
                return selected

    return selected

@st.cache_data(ttl=3600)
def translate_sentences(sentences):
    """Translate selected article sentences for personal study."""
    translated = []
    translator = GoogleTranslator(source="ko", target="en")

    for sentence in sentences:
        try:
            result = translator.translate(sentence)
            if result:
                translated.append(result.strip())
        except Exception:
            # Keep going if one sentence hits a translation-rate limit.
            continue

    return translated

def choose_difficult_sentence(sentences):
    if not sentences:
        return ""

    patterns = [
        r"\bwhich\b", r"\bthat\b", r"\bwhile\b", r"\balthough\b",
        r"\bdespite\b", r"\bbecause\b", r"\baccording to\b",
        r"\bwhile\b", r"\b(?:has|have|had)\b", r"\b(?:is|are|was|were)\b",
        r"\bto\s+\w+\b", r"\b(?:as|after|before|if|when)\b"
    ]

    scored = []
    for i, sentence in enumerate(sentences):
        score = min(len(sentence) / 45, 8)
        score += sum(
            bool(re.search(pattern, sentence, re.I))
            for pattern in patterns
        ) * 3

        # Avoid selecting a very simple first sentence when possible.
        if i == 0:
            score -= 1

        scored.append((score, sentence))

    return max(scored, key=lambda x: x[0])[1]

def explain_structure(sentence):
    s = sentence.strip()
    explanations = []

    if re.search(r"\b(has|have|had)\s+been\s+\w+ed\b", s, re.I):
        explanations.append(
            "**has/have been + p.p.** → 현재완료 수동태입니다. "
            "과거의 일이 현재까지 이어지는 결과나 상태를 나타냅니다."
        )
    elif re.search(r"\b(was|were|is|are|be)\s+\w+ed\b", s, re.I):
        explanations.append(
            "**be + p.p.** → 수동태입니다. 행동을 한 사람보다 "
            "행동을 받은 대상에 초점을 둡니다."
        )

    if re.search(r"\bwhich\b", s, re.I):
        explanations.append(
            "**which + 동사 ...** → 앞의 명사나 앞 문장 내용을 "
            "설명하는 관계대명사절입니다."
        )
    if re.search(r"\bthat\b", s, re.I):
        explanations.append(
            "**that + 주어 + 동사** → 내용을 이어 주는 명사절 또는 "
            "관계절로 사용될 수 있습니다."
        )
    if re.search(r"\bwhile\b", s, re.I):
        explanations.append(
            "**while + 주어 + 동사** → '~하는 동안' 또는 두 상황의 "
            "대조를 나타냅니다."
        )
    if re.search(r"\balthough\b", s, re.I):
        explanations.append(
            "**although + 주어 + 동사** → '~이지만'이라는 양보절입니다."
        )
    if re.search(r"\bdespite\b", s, re.I):
        explanations.append(
            "**despite + 명사/동명사** → '~에도 불구하고'라는 뜻입니다."
        )
    if re.search(r"\bbecause\b", s, re.I):
        explanations.append(
            "**because + 주어 + 동사** → 원인이나 이유를 설명합니다."
        )
    if re.search(r"\baccording to\b", s, re.I):
        explanations.append(
            "**according to + 명사** → '~에 따르면'이라는 출처를 나타냅니다."
        )
    if re.search(r"\bto\s+\w+\b", s, re.I):
        explanations.append(
            "**to + 동사원형** → 목적이나 앞으로 할 행동을 나타내는 "
            "to부정사로 쓰일 수 있습니다."
        )

    if not explanations:
        explanations.append(
            "먼저 **주어(S) + 동사(V)**를 찾고, 그 뒤의 목적어(O), "
            "보어(C), 수식어를 차례로 붙여 읽으면 됩니다."
        )

    return explanations

def render_article(item, display_rank):
    category = item["category"]
    badge = "🌎 INTERNATIONAL TOP 1" if category == "국제" else f"🏆 NEWS TOP {display_rank}"

    st.markdown(f"## {badge}")
    st.markdown(f"### {item['title']}")
    st.link_button("🇰🇷 매일경제 원문 보기", item["link"])

    paragraphs = get_article_paragraphs(item["link"])
    source_sentences = select_source_sentences(paragraphs, max_sentences=10)
    english_sentences = translate_sentences(source_sentences)

    st.markdown("#### 🇺🇸 English Summary")

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

    else:
        st.warning("기사 본문을 가져오거나 영어로 변환하지 못했습니다.")

news = load_news()

if len(news) < 6:
    st.error(
        f"매일경제 뉴스 종합 TOP 5 + 국제 TOP 1을 모두 가져오지 못했습니다. "
        f"현재 {len(news)}개를 가져왔습니다. 잠시 후 다시 실행해 주세요."
    )
    if news:
        st.info("가져온 기사만 표시합니다.")
else:
    st.success("뉴스 종합 TOP 5 + 국제 TOP 1을 가져왔습니다.")

for index, item in enumerate(news, 1):
    if item["category"] == "국제":
        render_article(item, 0)
    else:
        render_article(item, item["rank"])

    if index < len(news):
        st.divider()

st.divider()
st.caption(
    "매일경제 공식 인기뉴스 페이지의 뉴스 종합 TOP 5와 국제 TOP 1을 사용합니다. "
    "사진·포토 캡션은 제외하며, 기사 본문을 바탕으로 영어 학습용 문장을 제공합니다."
)
