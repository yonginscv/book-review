#!/usr/bin/env python3
"""Convert book-review markdown articles to a readable single HTML file."""

import re
import sys
import html
from pathlib import Path


def parse_markdown(text: str) -> dict:
    """Parse the structured markdown into a dict with title and articles."""
    lines = text.splitlines()

    # Extract main title (first # heading)
    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Split into article blocks by ## headings
    articles = []
    current_block = []
    for line in lines:
        if line.startswith("## ") and current_block:
            articles.append("\n".join(current_block))
            current_block = [line]
        elif line.startswith("## "):
            current_block = [line]
        else:
            if current_block:
                current_block.append(line)

    if current_block:
        articles.append("\n".join(current_block))

    parsed_articles = []
    for block in articles:
        block_lines = block.splitlines()
        if not block_lines:
            continue

        # Article heading: ## [N] [section] headline
        heading = block_lines[0][3:].strip()  # remove "## "
        match = re.match(r"\[(\d+)\]\s*(\[.*?\])?\s*(.*)", heading)
        if match:
            num = match.group(1)
            section = (match.group(2) or "").strip("[]")
            headline = match.group(3).strip()
        else:
            num = ""
            section = ""
            headline = heading

        # Parse metadata lines (- **key:** value)
        meta = {}
        body_start = 1
        for i, line in enumerate(block_lines[1:], start=1):
            m = re.match(r"^-\s+\*\*(.+?):\*\*\s*(.*)", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                # Multi-line value: next lines without "-" that are not empty
                meta[key] = val
                body_start = i + 1
            elif line.strip() == "---" or line.strip() == "":
                if line.strip() == "---":
                    break
                if i > body_start - 1:
                    body_start = i + 1
            elif meta:
                # continuation of last meta value (e.g., multi-line subtitle)
                last_key = list(meta.keys())[-1]
                meta[last_key] += " " + line.strip()
                body_start = i + 1

        # Body is everything after metadata until the --- separator
        body_lines = []
        in_body = False
        for line in block_lines[body_start:]:
            if line.strip() == "---":
                break
            body_lines.append(line)

        body = "\n".join(body_lines).strip()

        parsed_articles.append({
            "num": num,
            "section": section,
            "headline": headline,
            "meta": meta,
            "body": body,
        })

    return {"title": title, "articles": parsed_articles}


def escape(text: str) -> str:
    return html.escape(text)


def render_html(data: dict) -> str:
    title = escape(data["title"])
    articles_html = []

    for art in data["articles"]:
        num = escape(art["num"])
        section = escape(art["section"])
        headline = escape(art["headline"])
        body = escape(art["body"])

        # Format body: wrap paragraphs
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        body_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)

        meta_rows = ""
        for key, val in art["meta"].items():
            meta_rows += f'<div class="meta-row"><span class="meta-key">{escape(key)}</span><span class="meta-val">{escape(val)}</span></div>\n'

        section_badge = f'<span class="section-badge">{section}</span>' if section else ""
        num_badge = f'<span class="article-num">{num}</span>' if num else ""

        articles_html.append(f"""
    <article>
      <div class="article-header">
        <div class="article-meta-top">{num_badge}{section_badge}</div>
        <h2 class="article-title">{headline}</h2>
        <div class="meta">{meta_rows}</div>
      </div>
      <div class="article-body">{body_html}</div>
    </article>""")

    articles_joined = "\n".join(articles_html)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #faf9f7;
      --surface: #ffffff;
      --border: #e8e4de;
      --text-primary: #1a1814;
      --text-secondary: #5a5550;
      --text-muted: #9a918a;
      --accent: #c0392b;
      --accent-light: #f9f0ef;
      --badge-bg: #f0ede8;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background: var(--bg);
      color: var(--text-primary);
      font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
      font-size: 17px;
      line-height: 1.9;
      padding: 40px 20px 80px;
    }}

    header {{
      max-width: 780px;
      margin: 0 auto 56px;
      padding-bottom: 24px;
      border-bottom: 2px solid var(--accent);
    }}

    header h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: -0.02em;
    }}

    .article-count {{
      margin-top: 6px;
      font-size: 0.85rem;
      color: var(--text-muted);
    }}

    article {{
      max-width: 780px;
      margin: 0 auto 48px;
      background: var(--surface);
      border-radius: 12px;
      border: 1px solid var(--border);
      overflow: hidden;
      box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }}

    .article-header {{
      padding: 28px 32px 20px;
      border-bottom: 1px solid var(--border);
    }}

    .article-meta-top {{
      display: flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 12px;
    }}

    .article-num {{
      display: inline-block;
      background: var(--accent);
      color: white;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 2px 9px;
      border-radius: 20px;
      letter-spacing: 0.02em;
    }}

    .section-badge {{
      display: inline-block;
      background: var(--badge-bg);
      color: var(--text-secondary);
      font-size: 0.78rem;
      padding: 2px 10px;
      border-radius: 20px;
    }}

    .article-title {{
      font-size: 1.25rem;
      font-weight: 700;
      line-height: 1.45;
      color: var(--text-primary);
      letter-spacing: -0.02em;
      margin-bottom: 16px;
    }}

    .meta {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}

    .meta-row {{
      display: flex;
      gap: 10px;
      font-size: 0.83rem;
      color: var(--text-muted);
    }}

    .meta-key {{
      font-weight: 600;
      color: var(--text-secondary);
      white-space: nowrap;
    }}

    .meta-val {{
      color: var(--text-muted);
    }}

    .article-body {{
      padding: 28px 32px 32px;
    }}

    .article-body p {{
      font-size: 1rem;
      line-height: 1.95;
      color: var(--text-primary);
      margin-bottom: 1.1em;
      word-break: keep-all;
      overflow-wrap: break-word;
    }}

    .article-body p:last-child {{
      margin-bottom: 0;
    }}

    @media (max-width: 600px) {{
      body {{
        font-size: 16px;
        padding: 24px 12px 60px;
      }}
      .article-header,
      .article-body {{
        padding: 20px;
      }}
      .article-title {{
        font-size: 1.1rem;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <div class="article-count">총 {len(data['articles'])}건</div>
  </header>
  {articles_joined}
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("사용법: python md_to_html.py <input.md> [output.html]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다 — {input_path}")
        sys.exit(1)

    output_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else input_path.with_suffix(".html")

    text = input_path.read_text(encoding="utf-8")
    data = parse_markdown(text)
    html_content = render_html(data)
    output_path.write_text(html_content, encoding="utf-8")

    print(f"완료: {output_path}  ({len(data['articles'])}개 기사)")


if __name__ == "__main__":
    main()
