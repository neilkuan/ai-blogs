#!/usr/bin/env python3
"""
Extract new changelog sections from upstream CHANGELOG.md
and translate them to Traditional Chinese using Claude API.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import subprocess


def _parse_version(v: str) -> tuple:
    """Parse a version string like '2.1.98' into a comparable tuple (2, 1, 98)."""
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def extract_versions_between(changelog_text: str, latest_tag: str, last_tag: str) -> str:
    """
    Extract all changelog sections from latest_tag down to (but not including) last_tag.
    If last_tag is 'none', extract only the latest_tag section.

    Uses numeric version comparison so that skipped version numbers
    (e.g. tag v2.1.100 exists but CHANGELOG only has ## 2.1.98) are handled correctly.
    """
    # Strip leading 'v' from tags if present for matching
    latest_ver = latest_tag.lstrip("v")
    last_ver = last_tag.lstrip("v") if last_tag != "none" else None

    latest_tuple = _parse_version(latest_ver)
    last_tuple = _parse_version(last_ver) if last_ver else None

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

    # Collect sections newer than last_tag
    # Sections are ordered newest-first in CHANGELOG; we want everything
    # from the top down to (but not including) the last processed version.
    result_sections = []

    for version, content in sections:
        ver_tuple = _parse_version(version)

        # Stop when we reach a version <= last processed version
        if last_tuple and ver_tuple <= last_tuple:
            break

        result_sections.append(content)

        # If no last_ver (first run), only take the first (latest) section
        if not last_tuple:
            break

    if not result_sections:
        # No matching sections found — the target tag likely has no changelog entry
        print(f"   ⚠️ No changelog section found newer than {last_ver or 'none'} (upstream may not have updated CHANGELOG.md for {latest_ver})")
        return ""

    print(f"   Found {len(result_sections)} version(s) to translate")
    return "\n\n".join(result_sections)


def translate_changelog(text: str) -> str:
    """Translate changelog text to Traditional Chinese using kiro-cli headless mode."""
    prompt = """請將以下 Claude Code changelog 翻譯成繁體中文。

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
5. 如果翻譯後意思可能不明確，可以在括號內附上英文原文
6. 只輸出翻譯結果，不要加任何前言或說明

以下是要翻譯的內容：

""" + text

    result = subprocess.run(
        ["kiro-cli", "chat", "--no-interactive", "--wrap", "never", prompt],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"❌ kiro-cli failed (exit {result.returncode}): {result.stderr}")
        sys.exit(1)

    # Strip ANSI escape codes from output
    output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
    # Remove blockquote prefix kiro-cli may add to lines
    output = re.sub(r'^> ', '', output, flags=re.MULTILINE)
    return output.strip()


def markdown_to_html_content(md_text: str) -> str:
    """Convert markdown to basic HTML (headings, lists, code, bold, links)."""
    import html as html_mod

    lines = md_text.split("\n")
    html_lines = []
    in_list = False

    def _inline_markup(raw: str) -> str:
        """Apply inline code and bold markup safely with proper escaping."""
        # Preserve backtick content before escaping
        code_blocks = {}
        counter = [0]
        def _save_code(m):
            key = f"\x00CODE{counter[0]}\x00"
            code_blocks[key] = f'<code class="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-indigo-600 dark:text-indigo-300 text-sm">{html_mod.escape(m.group(1))}</code>'
            counter[0] += 1
            return key
        text = re.sub(r'`([^`]+)`', _save_code, raw)
        # Preserve bold content before escaping
        bold_blocks = {}
        def _save_bold(m):
            key = f"\x00BOLD{counter[0]}\x00"
            bold_blocks[key] = f'<strong>{html_mod.escape(m.group(1))}</strong>'
            counter[0] += 1
            return key
        text = re.sub(r'\*\*([^*]+)\*\*', _save_bold, text)
        # Escape everything else
        text = html_mod.escape(text)
        # Restore preserved blocks
        for key, val in code_blocks.items():
            text = text.replace(key, val)
        for key, val in bold_blocks.items():
            text = text.replace(key, val)
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
            html_lines.append(f'<h3 class="text-lg font-semibold mt-6 mb-2 text-indigo-700 dark:text-indigo-300">{text}</h3>')
        elif stripped.startswith("## "):
            text = html_mod.escape(stripped[3:])
            html_lines.append(f'<h2 class="text-xl font-bold mt-8 mb-3 text-indigo-800 dark:text-indigo-200 border-b border-gray-200 dark:border-gray-700 pb-2">{text}</h2>')
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append('<ul class="list-disc list-inside space-y-1 text-gray-700 dark:text-gray-300">')
                in_list = True
            item = _inline_markup(stripped[2:])
            html_lines.append(f"<li>{item}</li>")
        else:
            text = _inline_markup(stripped)
            html_lines.append(f'<p class="text-gray-700 dark:text-gray-300 leading-relaxed">{text}</p>')

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


THEME_SCRIPT = (
    "  <script>\n"
    "    const btn = document.getElementById('themeToggle');\n"
    "    const saved = localStorage.getItem('theme') || 'light';\n"
    "    applyTheme(saved);\n"
    "    function applyTheme(t) {\n"
    "      document.documentElement.classList.toggle('dark', t === 'dark');\n"
    "      btn.textContent = t === 'dark' ? '\\u2600\\uFE0F 淺色' : '\\uD83C\\uDF19 深色';\n"
    "      localStorage.setItem('theme', t);\n"
    "    }\n"
    "    function toggleTheme() {\n"
    "      applyTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark');\n"
    "    }\n"
    "  </script>\n"
)

PAGE_STYLE = (
    '<script src="https://cdn.tailwindcss.com"></script>\n'
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">\n'
    "<script>\n"
    "tailwind.config = {\n"
    "  darkMode: 'class',\n"
    "  theme: {\n"
    "    extend: {\n"
    "      colors: {\n"
    "        darkbg: '#0f172a',\n"
    "        cardbg: '#1e293b',\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "}\n"
    "</script>\n"
    "<style>\n"
    "  body { font-family: 'Noto Sans TC', sans-serif; }\n"
    "</style>\n"
)


def generate_version_html_pages(translated: str):
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

    cc_dir = Path("cc")
    cc_dir.mkdir(exist_ok=True)

    for version, content in sections:
        slug = f"claude-code-changelog-{version}"
        html_content = markdown_to_html_content(content)
        ev = html_mod.escape(version)

        page = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code {ev} 更新日誌</title>
{PAGE_STYLE}
</head>
<body class="bg-gray-50 dark:bg-darkbg text-gray-900 dark:text-gray-100 min-h-screen transition-colors">
  <div class="max-w-3xl mx-auto px-4 py-12">
    <nav class="mb-8 flex justify-between items-center">
      <a href="index.html" class="text-indigo-600 dark:text-indigo-400 hover:underline text-sm">&larr; 所有版本</a>
      <button id="themeToggle" onclick="toggleTheme()" class="px-3 py-1 text-sm border rounded-full border-gray-300 dark:border-gray-600 hover:border-indigo-500 transition-colors">🌙 深色</button>
    </nav>
    <header class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-2">Claude Code {ev} 更新日誌</h1>
      <p class="text-gray-500 dark:text-gray-400 text-sm">翻譯自 <a href="https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md" class="text-indigo-600 dark:text-indigo-400 hover:underline">官方 CHANGELOG</a></p>
    </header>
    <article class="bg-white dark:bg-cardbg rounded-2xl p-6 sm:p-8 shadow-lg space-y-3">
{html_content}
    </article>
    <footer class="mt-12 text-center text-gray-400 dark:text-gray-500 text-xs">
      此頁面由自動化流程產生，僅供參考。
    </footer>
  </div>
{THEME_SCRIPT}
</body>
</html>"""

        html_path = cc_dir / f"{slug}.html"
        html_path.write_text(page, encoding="utf-8")
        print(f"📄 Generated {html_path}")

    # Generate cc/index.html listing all versions
    generate_cc_index(cc_dir)

    # Ensure metadata.json has one entry for cc index
    meta_path = Path("metadata.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    # Remove old per-version entries
    meta = {k: v for k, v in meta.items() if not k.startswith("claude-code-changelog-")}
    meta["cc"] = {
        "title": "Claude Code 更新日誌",
        "description": "Claude Code 各版本更新內容（繁體中文翻譯）。",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"📝 Updated metadata.json")


def generate_cc_index(cc_dir: Path):
    """Generate cc/index.html that lists all changelog versions."""
    import html as html_mod

    # Find all changelog HTML files, sorted by version descending
    def _version_key(p):
        v = p.stem.replace("claude-code-changelog-", "")
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0,)
    files = sorted(cc_dir.glob("claude-code-changelog-*.html"), key=_version_key, reverse=True)
    items = []
    for f in files:
        version = f.stem.replace("claude-code-changelog-", "")
        ev = html_mod.escape(version)
        items.append(
            f'<li class="border-b border-gray-200 dark:border-gray-700 last:border-b-0">'
            f'<a href="{html_mod.escape(f.name)}" class="block px-2 py-4 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">'
            f'<span class="text-indigo-600 dark:text-indigo-400 font-medium">v{ev}</span>'
            f'</a></li>'
        )
    items_html = "\n".join(items)

    page = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code 更新日誌</title>
{PAGE_STYLE}
</head>
<body class="bg-gray-50 dark:bg-darkbg text-gray-900 dark:text-gray-100 min-h-screen transition-colors">
  <div class="max-w-3xl mx-auto px-4 py-12">
    <nav class="mb-8 flex justify-between items-center">
      <a href="../index.html" class="text-indigo-600 dark:text-indigo-400 hover:underline text-sm">&larr; 返回文章列表</a>
      <button id="themeToggle" onclick="toggleTheme()" class="px-3 py-1 text-sm border rounded-full border-gray-300 dark:border-gray-600 hover:border-indigo-500 transition-colors">🌙 深色</button>
    </nav>
    <header class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-2">Claude Code 更新日誌</h1>
      <p class="text-gray-500 dark:text-gray-400 text-sm">各版本更新內容（繁體中文翻譯）</p>
    </header>
    <ul class="bg-white dark:bg-cardbg rounded-2xl p-4 shadow-lg">
{items_html}
    </ul>
    <footer class="mt-12 text-center text-gray-400 dark:text-gray-500 text-xs">
      此頁面由自動化流程產生，僅供參考。
    </footer>
  </div>
{THEME_SCRIPT}
</body>
</html>"""

    index_path = cc_dir / "index.html"
    index_path.write_text(page, encoding="utf-8")
    print(f"📄 Generated {index_path}")


def main():
    target_tag = os.environ["TARGET_TAG"]
    last_tag = os.environ.get("LAST_TAG", "none")

    # Read upstream changelog
    upstream = Path("upstream_changelog.md").read_text(encoding="utf-8")

    total_start = time.time()

    # Extract relevant sections
    t0 = time.time()
    print(f"📋 Extracting changelog: {target_tag} (since: {last_tag})")
    new_content = extract_versions_between(upstream, target_tag, last_tag)
    print(f"   ⏱ Extract: {time.time() - t0:.1f}s")

    if not new_content.strip():
        print("⚠️ No new content found — upstream tag has no new changelog entry, updating state only.")
        Path(".last_processed_version").write_text(target_tag, encoding="utf-8")
        print(f"📌 Updated state: {target_tag}")
        sys.exit(0)

    print(f"📝 Content to translate ({len(new_content)} chars):\n{new_content[:300]}...")

    # Translate
    t0 = time.time()
    print("🤖 Translating via kiro-cli...")
    translated = translate_changelog(new_content)
    print(f"   ⏱ Translate: {time.time() - t0:.1f}s")

    # Append to existing translated changelog (prepend new content after header)
    t0 = time.time()
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
    print(f"   ⏱ Write markdown: {time.time() - t0:.1f}s")

    # Generate per-version HTML pages
    t0 = time.time()
    generate_version_html_pages(translated)
    print(f"   ⏱ Generate HTML: {time.time() - t0:.1f}s")

    # Update state file
    Path(".last_processed_version").write_text(target_tag, encoding="utf-8")
    print(f"📌 Updated state: {target_tag}")
    print(f"🏁 Total: {time.time() - total_start:.1f}s")


if __name__ == "__main__":
    main()