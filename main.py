import os
import re
import json
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
RESULT_NUMBER = int(os.getenv("RESULT_NUMBER", "10"))
PROVIDER_CODES = json.loads(
    os.getenv("PROVIDER_CODES", '["01100401", "01100801", "01101001", "02100101"]')
)

BIGKINDS_BASE = "https://www.bigkinds.or.kr"
SEARCH_URL = f"{BIGKINDS_BASE}/api/news/search.do"
DETAIL_URL = f"{BIGKINDS_BASE}/news/detailView.do"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

COMMON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,zh-TW;q=0.7,zh;q=0.6",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": BIGKINDS_BASE,
    "Referer": f"{BIGKINDS_BASE}/v2/news/search.do",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

SYSTEM_PROMPT = """당신은 신문 서평 전문 분석가입니다.
제공된 뉴스 기사 목록에서 서평 대상 도서를 식별하고, 도서별로 정보를 추출·요약합니다.
하나의 기사에 여러 도서가 소개될 수 있고, 동일한 도서가 여러 기사에 등장할 수 있습니다.
모든 출력은 한국어로 작성합니다."""


def init_session() -> requests.Session:
    """GET BigKinds homepage to acquire session cookies."""
    session = requests.Session()
    resp = session.get(
        BIGKINDS_BASE,
        headers={"User-Agent": COMMON_HEADERS["User-Agent"]},
        timeout=15,
    )
    resp.raise_for_status()
    return session


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def search_articles(session: requests.Session, start_date: str, end_date: str) -> list:
    """Search for book review articles via BigKinds search API."""
    payload = {
        "indexName": "news",
        "searchKey": "(지음 OR  옮김)",
        "searchKeys": [{"orKeywords": ["지음, 옮김"]}],
        "byLine": "",
        "searchFilterType": "1",
        "searchScopeType": "1",
        "searchSortType": "date",
        "sortMethod": "date",
        "mainTodayPersonYn": "",
        "startDate": start_date,
        "endDate": end_date,
        "newsIds": [],
        "categoryCodes": [],
        "providerCodes": PROVIDER_CODES,
        "incidentCodes": [],
        "networkNodeType": "",
        "topicOrigin": "",
        "dateCodes": [],
        "editorialIs": False,
        "startNo": 1,
        "resultNumber": RESULT_NUMBER,
        "isTmUsable": False,
        "isNotTmUsable": False,
    }
    resp = session.post(SEARCH_URL, json=payload, headers=COMMON_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Search API error: {data.get('errorMessage')}")
    return data.get("resultList", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_article_detail(session: requests.Session, news_id: str) -> dict:
    """Fetch full article content for a given NEWS_ID."""
    params = {"docId": news_id, "returnCnt": "1", "sectionDiv": "1000"}
    resp = session.get(DETAIL_URL, params=params, headers=COMMON_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("detail", {})


def strip_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_user_prompt(articles: list) -> str:
    lines = [
        "다음은 최근 1주일간 수집된 신문 서평 기사입니다. 도서별로 정보를 추출하고 요약해주세요.\n",
        "---",
    ]
    for i, article in enumerate(articles, 1):
        date_raw = article.get("DATE", "")
        date_fmt = (
            f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
            if len(date_raw) == 8
            else date_raw
        )
        content = strip_html(article.get("CONTENT", ""))
        lines.append(
            f"[기사 {i}]\n"
            f"신문사: {article.get('PROVIDER', '')}\n"
            f"제목: {article.get('TITLE', '')}\n"
            f"소제목: {article.get('SUB_TITLE', '')}\n"
            f"날짜: {date_fmt}\n"
            f"본문: {content}\n"
        )
    lines.append("---\n")
    lines.append(
        "## 요청사항\n\n"
        "각 기사에서 언급된 도서를 모두 추출하고, 동일 도서는 하나로 묶어 아래 형식으로 출력하세요.\n\n"
        "## 도서 제목\n\n"
        "- **저자/역자:** (기사에 명시된 경우)\n"
        "- **출판사:** (기사에 명시된 경우)\n"
        "- **소개 신문사:** 동아일보 (2026-02-15), 조선일보 (2026-02-14)\n"
        "- **핵심 내용:** 도서의 주제, 주요 내용, 구성을 3~5문장으로 요약\n"
        "- **서평 관점:** 각 신문사가 이 책을 어떤 시각으로 바라보는지 간략히 정리. 비평적 견해나 추천 이유가 있으면 포함.\n\n"
        "### 중복 도서 처리 규칙\n\n"
        "- 도서 제목이 동일하면 반드시 하나의 항목으로 병합합니다.\n"
        "- 병합 시 \"소개 신문사\" 항목에 모든 출처를 나열합니다.\n"
        "- \"서평 관점\"에 신문사별 시각 차이가 있으면 구분하여 서술합니다."
    )
    return "\n".join(lines)


def call_openrouter(articles: list) -> str:
    """Send all articles to OpenRouter in a single batch request."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(articles)},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }
    resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def save_articles(articles: list) -> str:
    """Write collected articles to YYYY-MM-DD-기사.md."""
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}-기사.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {today} 수집 기사 목록\n\n")
        for i, article in enumerate(articles, 1):
            date_raw = article.get("DATE", "")
            date_fmt = (
                f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
                if len(date_raw) == 8
                else date_raw
            )
            content = strip_html(article.get("CONTENT", ""))
            f.write(f"## [{i}] {article.get('TITLE', '')}\n\n")
            f.write(f"- **신문사:** {article.get('PROVIDER', '')}\n")
            f.write(f"- **소제목:** {article.get('SUB_TITLE', '')}\n")
            f.write(f"- **날짜:** {date_fmt}\n\n")
            f.write(f"{content}\n\n")
            f.write("---\n\n")
    return filename


def save_result(content: str) -> str:
    """Write summary to YYYY-MM-DD-서평.md."""
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}-서평.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {today} 신문 서평 요약\n\n")
        f.write(content)
        f.write("\n")
    return filename


def main():
    print("=== BigKinds 서평 수집 시작 ===")

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=6)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")
    print(f"수집 기간: {start_date} ~ {end_date}")
    print(f"신문사 코드: {PROVIDER_CODES}")
    print(f"최대 기사 수: {RESULT_NUMBER}")

    # 1. Initialize session (get BigKinds cookies)
    print("\n[1/4] 세션 초기화 중...")
    session = init_session()
    print("    쿠키 획득 완료")

    # 2. Search articles
    print("\n[2/4] 기사 검색 중...")
    articles = search_articles(session, start_date, end_date)
    print(f"    {len(articles)}개 기사 발견")
    if not articles:
        print("검색된 기사가 없습니다. 종료합니다.")
        return

    # 3. Fetch article details (5-second delay between requests)
    print("\n[3/4] 기사 상세 내용 수집 중...")
    for i, article in enumerate(articles, 1):
        news_id = article.get("NEWS_ID")
        title_preview = article.get("TITLE", "")[:50]
        print(f"    [{i}/{len(articles)}] {title_preview}...")

        if news_id:
            detail = fetch_article_detail(session, news_id)
            if detail.get("CONTENT"):
                article["CONTENT"] = detail["CONTENT"]

        if i < len(articles):
            time.sleep(5)

    print(f"    상세 수집 완료")

    # 4. Save collected articles
    print("\n[4/5] 수집 기사 저장 중...")
    articles_filename = save_articles(articles)
    print(f"    저장 완료: {articles_filename}")

    # 5. AI batch summarization

    print("\n[5/5] AI 서평 분석 중...")
    print(f"    모델: {OPENROUTER_MODEL}")
    summary = call_openrouter(articles)

    # Save
    filename = save_result(summary)
    print(f"\n=== 완료: {articles_filename}, {filename} ===")


if __name__ == "__main__":
    main()
