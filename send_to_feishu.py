# -*- coding: utf-8 -*-
"""读取 ai_news_result.txt，通过飞书自定义机器人 Webhook 推送交互式消息卡片。"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
IN_FILE = ROOT / "ai_news_result.txt"

# 行格式：1. 标题（分类），下一行可为原文链接（https://...）
LINE_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*（([^）]+)）\s*$")
URL_FOLLOW = re.compile(r"^https?://\S+$", re.IGNORECASE)


def _md_safe_url(url: str) -> str:
    return url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")

CATEGORY_EMOJI = {
    "科技": "💡",
    "民生": "🏠",
    "社会": "📰",
    "财经": "📈",
    "娱乐": "🎬",
}

# 飞书 lark_md 支持的 font color
CATEGORY_COLOR = {
    "科技": "blue",
    "民生": "green",
    "社会": "grey",
    "财经": "orange",
    "娱乐": "violet",
}

CARD_MD_MAX = 12000


def _short_source(source: str) -> str:
    """把抓取的 source（微博热搜/抖音热榜/腾讯新闻热点等）压缩成更短的 App 名。"""
    s = (source or "").strip()
    if "微博" in s:
        return "微博"
    if "抖音" in s:
        return "抖音"
    if "知乎" in s:
        return "知乎"
    if "头条" in s:
        return "头条"
    if "腾讯" in s:
        return "腾讯新闻"
    if "百度" in s:
        return "百度"
    if "B站" in s:
        return "B站"
    return s


def load_dotenv_if_present():
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                # 只有当变量不存在或值为空时才写入，避免把空字符串当成已配置。
                if k and (k not in os.environ or not str(os.environ.get(k, "")).strip()):
                    os.environ[k] = v
    except OSError:
        pass


def parse_news_items(text: str) -> list[dict]:
    items: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        m = LINE_RE.match(line)
        if m:
            rec = {
                "n": int(m.group(1)),
                "title": m.group(2).strip(),
                "cat": m.group(3).strip(),
            }
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and URL_FOLLOW.match(lines[j].strip()):
                rec["url"] = lines[j].strip()
                i = j + 1
            else:
                i += 1
            items.append(rec)
        else:
            items.append({"raw": line})
            i += 1
    return items


def _format_item_line(it: dict) -> str:
    if "raw" in it:
        return it["raw"]

    # it["cat"] 可能是：分类 或 分类|来源（例如 社会|微博热搜）
    cat_and_src = (it.get("cat") or "").strip()
    cat = cat_and_src
    src = ""
    if "|" in cat_and_src:
        cat, src = cat_and_src.split("|", 1)

    emoji = CATEGORY_EMOJI.get(cat, "📌")
    color = CATEGORY_COLOR.get(cat, "grey")
    cat_html = f"<font color='{color}'>{cat}</font>"
    line = f"**{it['n']}.** {emoji} {it['title']}　{cat_html}"

    src_short = _short_source(src)
    if src_short:
        line += f"　来自{src_short}"
    u = (it.get("url") or "").strip()
    if u:
        line += f"　[查看原文]({_md_safe_url(u)})"
    return line


def build_markdown_chunks(text: str) -> list[str]:
    items = parse_news_items(text)
    structured = any("n" in x for x in items)

    if not structured:
        body = text.strip()
        if len(body) > CARD_MD_MAX:
            body = body[: CARD_MD_MAX - 30] + "\n\n*（内容过长已截断）*"
        return [body]

    n = sum(1 for x in items if "n" in x)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header_md = f"📊 **今日精选** · 共 **{n}** 条 · 更新于 {now}\n\n"

    lines = [_format_item_line(it) for it in items]
    body = header_md + "\n\n".join(lines)
    if len(body) <= CARD_MD_MAX:
        return [body]

    # 过长时分片：首块带统计头，后续仅列表行
    chunks: list[str] = []
    current = header_md
    for it in items:
        piece = _format_item_line(it) if "n" in it or "raw" in it else ""
        if not piece:
            continue
        add = ("\n\n" if current and not current.endswith("\n\n") else "") + piece
        if len(current) + len(add) > CARD_MD_MAX and len(current) > len(header_md):
            chunks.append(current.rstrip())
            current = piece
        else:
            current += add
    if current.strip():
        chunks.append(current.rstrip())
    return chunks if chunks else [body[: CARD_MD_MAX]]


def build_interactive_card(text: str) -> dict:
    chunks = build_markdown_chunks(text)
    elements = []
    for i, chunk in enumerate(chunks):
        elements.append(
            {
                "tag": "markdown",
                "content": chunk,
                "text_align": "left",
                "text_size": "normal_v2",
                "margin": "0px 0px 12px 0px" if i < len(chunks) - 1 else "0px",
            }
        )
    elements.append(
        {
            "tag": "markdown",
            "content": "*数据由热点抓取与 AI 摘要自动生成，仅供参考。*",
            "text_align": "left",
            "text_size": "normal_v2",
            "margin": "8px 0px 0px 0px",
        }
    )

    now = datetime.now()
    subtitle = f"{now.year}年{now.month}月{now.day}日"

    card = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "style": {
                "text_size": {
                    "normal_v2": {
                        "default": "normal",
                        "pc": "normal",
                        "mobile": "heading",
                    }
                }
            },
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 16px 12px",
            "elements": elements,
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "每日实时热点 · 舆情早报",
            },
            "subtitle": {
                "tag": "plain_text",
                "content": subtitle,
            },
            "template": "blue",
            "padding": "12px 12px 12px 12px",
        },
    }
    return {"msg_type": "interactive", "card": card}


def send_feishu_message(webhook: str, content: str):
    # 整卡 JSON 不宜过大；若原文极长，先截断再构图
    max_raw = max(20000, CARD_MD_MAX * 3)
    if len(content) > max_raw:
        content = content[: max_raw - 30] + "\n...(原文过长已截断)"

    use_text = os.environ.get("FEISHU_USE_TEXT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if use_text:
        max_len = 15000
        body = content
        if len(body) > max_len:
            body = body[: max_len - 20] + "\n...(内容过长已截断)"
        data = {
            "msg_type": "text",
            "content": {"text": "【每日实时热点舆情早报】\n\n" + body},
        }
    else:
        data = build_interactive_card(content)

    res = requests.post(webhook, json=data, timeout=30)
    try:
        body_json = res.json()
    except Exception:
        print("飞书响应非 JSON: ", res.status_code, res.text[:500], file=sys.stderr)
        sys.exit(1)
    print("飞书推送结果：", json.dumps(body_json, ensure_ascii=False))
    if res.status_code >= 400:
        sys.exit(1)
    if body_json.get("code") not in (0, None) and str(body_json.get("code")) != "0":
        sys.exit(1)


if __name__ == "__main__":
    load_dotenv_if_present()
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        print(
            "请设置环境变量 FEISHU_WEBHOOK，或在 .env 中写入 FEISHU_WEBHOOK=https://...",
            file=sys.stderr,
        )
        sys.exit(1)
    if not IN_FILE.is_file():
        print("未找到 ai_news_result.txt，请先运行 ai_news_filter.py", file=sys.stderr)
        sys.exit(1)
    text = IN_FILE.read_text(encoding="utf-8")
    send_feishu_message(webhook, text)
