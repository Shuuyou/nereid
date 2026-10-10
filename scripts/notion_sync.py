#!/usr/bin/env python3
"""Notion 竞赛文档同步器

用法：
  python scripts/notion_sync.py --page SecAgent          # 全量重建主文档
  python scripts/notion_sync.py --md docs/02-系统架构.md --parent <page_id>  # 单个 md→子页面

设计：Markdown → Notion blocks 转换器 + 页面全量重建（保证逻辑自洽）。
环境变量：NOTION_TOKEN / NOTION_PAGE_ID（或命令行参数覆盖）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_TOKEN = os.environ.get("NOTION_TOKEN", "")
DEFAULT_PAGE = os.environ.get("NOTION_PAGE_ID", "3f5d3aea-8397-80d8-bb09-e1ec9ac32da3")


def rt(text: str, **ann) -> dict:
    """rich_text 构造（自动截断 2000 字符）"""
    return {"type": "text", "text": {"content": text[:2000]}, "annotations": {
        "bold": ann.get("bold", False), "italic": ann.get("italic", False),
        "code": ann.get("code", False), "strikethrough": False, "underline": False,
        "color": ann.get("color", "default"),
    }}


def parse_inline(text: str) -> list[dict]:
    """解析 **bold** `code` [link](url) 为 rich_text 数组"""
    out: list[dict] = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            out.append(rt(text[pos:m.start()]))
        tok = m.group(0)
        if tok.startswith("**"):
            out.append(rt(tok[2:-2], bold=True))
        elif tok.startswith("`"):
            out.append(rt(tok[1:-1], code=True))
        elif tok.startswith("["):
            label, _, url = tok[1:-1].partition("](")
            out.append({"type": "text", "text": {"content": label[:2000], "link": {"url": url}},
                        "annotations": {"bold": False, "italic": False, "code": False,
                                        "strikethrough": False, "underline": False, "color": "default"}})
        pos = m.end()
    if pos < len(text):
        out.append(rt(text[pos:]))
    return out or [rt("")]


def md_to_blocks(md: str) -> list[dict]:
    """Markdown → Notion blocks"""
    blocks: list[dict] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        # 代码块
        if line.startswith("```"):
            lang = line[3:].strip() or "plain text"
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            code = "\n".join(buf)
            for chunk in [code[j:j + 2000] for j in range(0, len(code), 2000)] or [""]:
                blocks.append({"object": "block", "type": "code",
                               "code": {"rich_text": [{"type": "text", "text": {"content": chunk}}],
                                        "language": lang if lang in _LANGS else "plain text"}})
            continue
        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            lvl = min(len(m.group(1)), 3)
            blocks.append({"object": "block", "type": f"heading_{lvl}",
                           f"heading_{lvl}": {"rich_text": parse_inline(m.group(2))}})
            i += 1
            continue
        # 表格
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            table_rows = []
            all_rows = [header] + rows
            for r in all_rows:
                cells = [parse_inline(c) for c in (r + [""] * (len(header) - len(r)))[:len(header)]]
                table_rows.append({"object": "block", "type": "table_row",
                                   "table_row": {"cells": cells}})
            blocks.append({"object": "block", "type": "table",
                           "table": {"table_width": len(header), "has_column_header": True,
                                     "has_row_header": False, "children": table_rows}})
            continue
        # 引用 → callout
        if line.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> "))
                i += 1
            blocks.append({"object": "block", "type": "callout",
                           "callout": {"rich_text": parse_inline(" ".join(buf)),
                                       "icon": {"type": "emoji", "emoji": "💡"}}})
            continue
        # 分隔线
        if re.match(r"^(-{3,}|\*{3,})$", line.strip()):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue
        # 有序/无序列表
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)", line)
        if m:
            btype = "numbered_list_item" if re.match(r"\d", m.group(2)) else "bulleted_list_item"
            blocks.append({"object": "block", "type": btype,
                           btype: {"rich_text": parse_inline(m.group(3))}})
            i += 1
            continue
        # checkbox
        m = re.match(r"^-\s*\[([ xX])\]\s+(.*)", line)
        if m:
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": parse_inline(m.group(2)),
                                     "checked": m.group(1).lower() == "x"}})
            i += 1
            continue
        # 普通段落（合并连续非空行）
        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,4}\s|```|\||>|-{3,}|\*{3,}|\s*([-*+]|\d+[.)])\s)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        para = " ".join(buf)
        for chunk in [para[j:j + 2000] for j in range(0, len(para), 2000)] or [""]:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": parse_inline(chunk)}})
    return blocks


_LANGS = {"python", "javascript", "typescript", "json", "yaml", "bash", "shell", "sql",
          "cypher", "html", "css", "go", "rust", "java", "plain text", "markdown", "docker"}


class NotionClient:
    def __init__(self, token: str):
        self.token = token

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}",
                   "Notion-Version": NOTION_VERSION,
                   "Content-Type": "application/json"}
        try:
            import requests  # noqa: PLC0415
            for attempt in range(4):
                r = requests.request(method, NOTION_API + path, headers=headers,
                                     json=body, timeout=30)
                if r.status_code == 429 and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(f"Notion {method} {path} -> {r.status_code}: {r.text[:500]}")
                return r.json()
            return {}
        except ImportError:
            pass
        req = urllib.request.Request(
            NOTION_API + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers=headers)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                detail = e.read().decode()[:500]
                raise RuntimeError(f"Notion {method} {path} -> {e.code}: {detail}")
        return {}

    def children(self, block_id: str) -> list[dict]:
        out, cursor = [], None
        while True:
            path = f"/blocks/{block_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            r = self._req("GET", path)
            out += r.get("results", [])
            cursor = r.get("next_cursor")
            if not r.get("has_more"):
                return out

    def delete_block(self, block_id: str) -> None:
        self._req("DELETE", f"/blocks/{block_id}")

    def append(self, parent_id: str, blocks: list[dict]) -> None:
        for i in range(0, len(blocks), 90):
            self._req("PATCH", f"/blocks/{parent_id}/children",
                      {"children": blocks[i:i + 90]})
            time.sleep(0.4)

    def create_page(self, parent_id: str, title: str, icon: str | None = None) -> str:
        body = {"parent": {"page_id": parent_id},
                "properties": {"title": {"title": [{"text": {"content": title}}]}}}
        if icon:
            body["icon"] = {"type": "emoji", "emoji": icon}
        return self._req("POST", "/pages", body)["id"]

    def rebuild(self, page_id: str, blocks: list[dict]) -> None:
        """全量重建：删除全部子块后重排"""
        for b in self.children(page_id):
            self.delete_block(b["id"])
            time.sleep(0.15)
        self.append(page_id, blocks)


def heading(text: str, level: int = 1) -> dict:
    return {"object": "block", "type": f"heading_{level}",
            f"heading_{level}": {"rich_text": parse_inline(text)}}


def para(text: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": parse_inline(text)}}


def bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": parse_inline(text)}}


def callout(text: str, emoji: str = "💡") -> dict:
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": parse_inline(text), "icon": {"type": "emoji", "emoji": emoji}}}


def divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def todo(text: str, checked: bool = False) -> dict:
    return {"object": "block", "type": "to_do",
            "to_do": {"rich_text": parse_inline(text), "checked": checked}}


def child_page(title: str, emoji: str = "📄") -> dict:
    """注意：child_page 需要 Notion API 特殊处理，这里用 mention/page 链接代替：
    实际创建子页面通过 create_page API，再在父页插入 link_to_page 块"""
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": parse_inline(f"{emoji} {title}")}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    ap.add_argument("--page", default=DEFAULT_PAGE)
    ap.add_argument("--md", help="同步单个 markdown 文件为子页面")
    ap.add_argument("--title", help="子页面标题")
    args = ap.parse_args()

    if not args.token:
        print("需要 --token 或 NOTION_TOKEN", file=sys.stderr)
        sys.exit(1)

    client = NotionClient(args.token)

    if args.md:
        md = open(args.md, encoding="utf-8").read()
        title = args.title or os.path.basename(args.md).replace(".md", "")
        blocks = md_to_blocks(md)
        # 找同名子页面或新建
        target = None
        for b in client.children(args.page):
            if b["type"] == "child_page" and b["child_page"]["title"] == title:
                target = b["id"]
        if not target:
            target = client.create_page(args.page, title)
        client.rebuild(target, blocks)
        print(f"synced {args.md} -> notion page {target}")
        return

    print("请使用 --md 指定文件，或用本模块 API 构建文档")
    sys.exit(1)


if __name__ == "__main__":
    main()
