#!/usr/bin/env python3
"""Generate 서평 from an existing YYYY-MM-DD-기사.md file."""

import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """당신은 신문 서평 전문 분석가입니다.
제공된 뉴스 기사 목록에서 서평 대상 도서를 식별하고, 도서별로 정보를 추출·요약합니다.
하나의 기사에 여러 도서가 소개될 수 있고, 동일한 도서가 여러 기사에 등장할 수 있습니다.
모든 출력은 한국어로 작성합니다."""


def parse_articles_from_md(text: str) -> list:
    """Parse YYYY-MM-DD-기사.md into a list of article dicts."""
    articles = []

    # Split on ## headings
    blocks = re.split(r"(?=^## )", text, flags=re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block.startswith("## "):
            continue

        lines = block.splitlines()
        heading = lines[0][3:].strip()  # strip "## "

        # Extract title: ## [N] [section] headline  OR  ## [N] headline
        m = re.match(r"\[\d+\]\s*(?:\[.*?\])?\s*(.*)", heading)
        title = m.group(1).strip() if m else heading

        meta = {}
        body_lines = []
        in_body = False

        for line in lines[1:]:
            if line.strip() == "---":
                break
            m2 = re.match(r"^-\s+\*\*(.+?):\*\*\s*(.*)", line)
            if m2 and not in_body:
                key = m2.group(1).strip()
                val = m2.group(2).strip()
                meta[key] = val
            elif line.strip() == "" and not in_body:
                if meta:
                    in_body = True
            else:
                if in_body or (meta and line.strip()):
                    in_body = True
                    body_lines.append(line)

        # Handle multi-line 소제목 (continuation lines before blank line)
        # Already handled above since we break on "---"

        date_raw = meta.get("날짜", "")
        # Normalize date: YYYY-MM-DD → kept as-is (build_user_prompt handles it)

        articles.append({
            "TITLE": title,
            "PROVIDER": meta.get("신문사", ""),
            "SUB_TITLE": meta.get("소제목", ""),
            "DATE": date_raw,
            "CONTENT": "\n".join(body_lines).strip(),
        })

    return articles


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
        lines.append(
            f"[기사 {i}]\n"
            f"신문사: {article.get('PROVIDER', '')}\n"
            f"제목: {article.get('TITLE', '')}\n"
            f"소제목: {article.get('SUB_TITLE', '')}\n"
            f"날짜: {date_fmt}\n"
            f"본문: {article.get('CONTENT', '')}\n"
        )
    lines.append("---\n")
    lines.append(
        "## 요청사항\n\n"
        "각 기사에서 언급된 도서를 모두 추출하고, 동일 도서는 하나로 묶어 아래 형식으로 출력하세요.\n\n"
        "## 도서 제목\n\n"
        "- **저자/역자:** (기사에 명시된 경우)\n"
        "- **출판사:** (기사에 명시된 경우)\n"
        "- **소개 신문사:** 동아일보 (2026-02-15), 조선일보 (2026-02-14)\n"
        "- **핵심 내용:** 도서의 주제, 주요 내용, 구성을 자세히 정리\n"
        "- **서평 관점:** 각 신문사가 이 책을 어떤 시각으로 바라보는지 간략히 정리. 비평적 견해나 추천 이유가 있으면 포함.\n\n"
        "### 중복 도서 처리 규칙\n\n"
        "- 도서 제목이 동일하면 반드시 하나의 항목으로 병합합니다.\n"
        "- 병합 시 \"소개 신문사\" 항목에 모든 출처를 나열합니다.\n"
        "- \"서평 관점\"에 신문사별 시각 차이가 있으면 구분하여 서술합니다."
    )
    return "\n".join(lines)


def call_openrouter(articles: list) -> str:
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


def main():
    if len(sys.argv) < 2:
        print("사용법: python summarize.py <YYYY-MM-DD-기사.md> [output.md]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다 — {input_path}")
        sys.exit(1)

    # Derive output path: YYYY-MM-DD-서평.md
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        stem = input_path.stem  # e.g. "2026-04-25-기사"
        date_prefix = re.match(r"(\d{4}-\d{2}-\d{2})", stem)
        if date_prefix:
            output_path = input_path.parent / f"{date_prefix.group(1)}-서평.md"
        else:
            output_path = input_path.with_name(input_path.stem + "-서평.md")

    print(f"입력: {input_path}")
    text = input_path.read_text(encoding="utf-8")

    print("기사 파싱 중...")
    articles = parse_articles_from_md(text)
    print(f"  {len(articles)}개 기사 파싱 완료")
    if not articles:
        print("파싱된 기사가 없습니다. 종료합니다.")
        sys.exit(1)

    print(f"AI 서평 분석 중... (모델: {OPENROUTER_MODEL})")
    summary = call_openrouter(articles)

    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", input_path.stem)
    date_label = date_match.group(1) if date_match else input_path.stem

    output_path.write_text(
        f"# {date_label} 신문 서평 요약\n\n{summary}\n",
        encoding="utf-8",
    )
    print(f"완료: {output_path}")


if __name__ == "__main__":
    main()
