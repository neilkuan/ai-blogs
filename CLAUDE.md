# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

`ai-blogs` 是一個靜態 HTML 文章集合，每篇文章為獨立的單一 HTML 檔案，使用 Tailwind CSS 樣式。

## 檔案命名規則

- `<slug>_1.html` — 原始版本文章
- `<slug>-branded.html` — 品牌化版本（通常包含額外品牌視覺元素）

## HTML 結構特性

- 所有 HTML 檔案為自包含（self-contained）的單頁文件
- 樣式使用 Tailwind CSS（inline 或 minified）
- 無建置工具、無套件管理員、無編譯步驟
- 直接用瀏覽器開啟即可預覽
