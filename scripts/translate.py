#!/usr/bin/env python3
"""
Extract new changelog sections from upstream CHANGELOG.md
and translate them to Traditional Chinese using Claude API.
"""

import json
import os
import re
import sys
from pathlib import Path

import anthropic


BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")


def extract_versions_between(changelog_text: str, latest_tag: str, last_tag: str) -> str:
    """
    Extract all changelog sections from latest_tag down to (but not including) last_tag.
    If last_tag is 'none', extract only the latest_tag section.
    """
    # Strip leading 'v' from tags if present for matching
    latest_ver = latest_tag.lstrip("v")
    last_ver = last_tag.lstrip("v") if last_tag != "none" else None

    # Split by version headers: ## x.y.z
    pattern = r"^(## \d+\.\d+\.\d+)"
    parts = re.split(pattern, changelog_text, flags=re.MULTILINE)

    # parts = ['preamble', '## 2.1.88', '\ncontent...', '## 2.1.87', '\ncontent...', ...]
    sections = []
    i = 1  # skip preamble
    while i < len(parts) - 1:
        header = parts[i].strip()
        body = parts[i + 1]
        version = header.replace("## ", "")
        sections.append((version, header + "\n" + body.strip()))
        i += 2

    # Collect sections between latest and last (exclusive)
    result_sections = []
    collecting = False

    for version, content in sections:
        if version == latest_ver:
            collecting = True
        if collecting:
            if last_ver and version == last_ver:
                break
            result_sections.append(content)

    if not result_sections:
        # Fallback: just grab the first section (latest)
        if sections:
            result_sections = [sections[0][1]]

    return "\n\n".join(result_sections)


def translate_changelog(text: str) -> str:
    """Translate changelog text to Traditional Chinese using Claude API."""
    client = anthropic.AnthropicBedrock(aws_region=BEDROCK_REGION)

    system_prompt = """你是一位專業的技術文件翻譯員，擅長將英文軟體 changelog 翻譯成繁體中文。

翻譯規則：
1. 保留以下不翻譯：
   - 技術專有名詞：API, SDK, CLI, hook, plugin, schema, cache, LRU, LSP, CJK, CRLF, stderr, stdin, JSON, JSONL, HTTP, WebSocket, tmux, iTerm2, PowerShell, Bash
   - 工具名稱：Claude Code, Cowork, Dispatch
   - 程式碼片段（反引號包裹的內容）
   - 環境變數名稱
   - 指令名稱（如 /stats, /usage, /btw, /env, /permissions）
2. 用口語化但專業的語氣
3. 保持 markdown 格式不變（## 標題、bullet points 等）
4. 版本號標題保持原樣
5. 如果翻譯後意思可能不明確，可以在括號內附上英文原文"""

    message = client.messages.create(
        model=BEDROCK_MODEL_ID,
        max_tokens=8192,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"請將以下 Claude Code changelog 翻譯成繁體中文：\n\n{text}",
            }
        ],
    )

    return message.content[0].text


def markdown_to_html_content(md_text: str) -> str:
    """Convert markdown to basic HTML (headings, lists, code, bold, links)."""
    import html as html_mod

    lines = md_text.split("\n")
    html_lines = []
    in_list = False

    def _inline_markup(text: str) -> str:
        """Apply inline code and bold markup on already-escaped text safely."""
        # Extract backtick content, escape it, then wrap in <code>
        def _code_repl(m):
            return f'<code class="px-1.5 py-0.5 bg-gray-800 rounded text-indigo-300 text-sm">{html_mod.escape(m.group(1))}</code>'
        text = re.sub(r'`([^`]+)`', _code_repl, text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
        return text

    for line in lines:
        stripped = line.strip()

        # Close list if needed
        if in_list and not stripped.startswith("- "):
            html_lines.append("</ul>")
            in_list = False

        if not stripped:
            html_lines.append("")
            continue

        # Headings
        if stripped.startswith("### "):
            text = html_mod.escape(stripped[4:])
            html_lines.append(f'<h3 class="text-lg font-semibold mt-6 mb-2 text-indigo-300">{text}</h3>')
        elif stripped.startswith("## "):
            text = html_mod.escape(stripped[3:])
            html_lines.append(f'<h2 class="text-xl font-bold mt-8 mb-3 text-indigo-200 border-b border-gray-700 pb-2">{text}</h2>')
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append('<ul class="list-disc list-inside space-y-1 text-gray-300">')
                in_list = True
            item = _inline_markup(stripped[2:])
            html_lines.append(f"<li>{item}</li>")
        else:
            text = _inline_markup(stripped)
            html_lines.append(f'<p class="text-gray-300 leading-relaxed">{text}</p>')

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def generate_version_html_pages(translated: str, target_tag: str):
    """Generate individual HTML pages for each translated version and update metadata.json."""
    import html as html_mod

    # Split translated text into per-version sections
    pattern = r"^(## \d+\.\d+\.\d+)"
    parts = re.split(pattern, translated, flags=re.MULTILINE)

    sections = []
    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip()
        body = parts[i + 1].strip()
        version = header.replace("## ", "")
        sections.append((version, header + "\n" + body))
        i += 2

    if not sections:
        print("⚠️ No version sections found for HTML generation")
        return

    # Load existing metadata
    meta_path = Path("metadata.json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {}

    for version, content in sections:
        slug = f"claude-code-changelog-{version}"
        html_content = markdown_to_html_content(content)
        escaped_version = html_mod.escape(version)

        page = f"""<!DOCTYPE html>
<html lang="zh-TW" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code {escaped_version} 更新日誌</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
<script>
tailwind.config = {{
  darkMode: 'class',
  theme: {{
    extend: {{
      colors: {{
        darkbg: '#0f172a',
        cardbg: '#1e293b',
      }}
    }}
  }}
}}
</script>
<style>
  body {{ font-family: 'Noto Sans TC', sans-serif; }}
</style>
</head>
<body class="dark:bg-darkbg bg-gray-50 dark:text-gray-100 text-gray-900 min-h-screen">
  <div class="max-w-3xl mx-auto px-4 py-12">
    <nav class="mb-8">
      <a href="../index.html" class="text-indigo-400 hover:text-indigo-300 text-sm">&larr; 返回文章列表</a>
    </nav>
    <header class="mb-8">
      <h1 class="text-3xl font-bold text-white mb-2">Claude Code {escaped_version} 更新日誌</h1>
      <p class="text-gray-400 text-sm">翻譯自 <a href="https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md" class="text-indigo-400 hover:underline">官方 CHANGELOG</a></p>
    </header>
    <article class="bg-cardbg rounded-2xl p-6 sm:p-8 shadow-lg space-y-3">
{html_content}
    </article>
    <footer class="mt-12 text-center text-gray-500 text-xs">
      此頁面由自動化流程產生，僅供參考。
    </footer>
  </div>
</body>
</html>"""

        cc_dir = Path("cc")
        cc_dir.mkdir(exist_ok=True)
        html_path = cc_dir / f"{slug}.html"
        html_path.write_text(page, encoding="utf-8")
        print(f"📄 Generated {html_path}")

        # Update metadata
        meta[slug] = {
            "title": f"Claude Code {version} 更新日誌",
            "description": f"Claude Code {version} 版本更新內容（繁體中文翻譯）。",
        }

    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"📝 Updated metadata.json with {len(sections)} version(s)")


def main():
    target_tag = os.environ["TARGET_TAG"]
    last_tag = os.environ.get("LAST_TAG", "none")

    # Read upstream changelog
    upstream = Path("upstream_changelog.md").read_text(encoding="utf-8")

    # Extract relevant sections
    print(f"📋 Extracting changelog: {target_tag} (since: {last_tag})")
    new_content = extract_versions_between(upstream, target_tag, last_tag)

    if not new_content.strip():
        print("⚠️ No new content found, skipping.")
        sys.exit(0)

    print(f"📝 Content to translate ({len(new_content)} chars):\n{new_content[:300]}...")

    # Translate
    print("🤖 Translating via Claude API...")
    translated = translate_changelog(new_content)

    # Append to existing translated changelog (prepend new content after header)
    output_path = Path("CHANGELOG_zh-TW.md")
    header = "# Claude Code 更新日誌（繁體中文）\n\n> 此文件由 AI 自動翻譯，僅供參考。原文請見 [CHANGELOG.md](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)\n\n"

    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        # Remove header from existing content
        existing_body = existing.split("\n\n", 2)[-1] if existing.startswith("# ") else existing
        final = header + translated + "\n\n" + existing_body
    else:
        final = header + translated + "\n"

    output_path.write_text(final, encoding="utf-8")
    print(f"✅ Wrote translated changelog to {output_path}")

    # Generate per-version HTML pages
    generate_version_html_pages(translated, target_tag)

    # Update state file
    Path(".last_processed_version").write_text(target_tag, encoding="utf-8")
    print(f"📌 Updated state: {target_tag}")


if __name__ == "__main__":
    main()