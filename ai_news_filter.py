# -*- coding: utf-8 -*-
"""读取 hot_news.json，调用 DeepSeek 做摘要、分类与过滤，输出 ai_news_result.txt。"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
IN_FILE = ROOT / "hot_news.json"
OUT_FILE = ROOT / "ai_news_result.txt"
OUT_TOP5_FILE = ROOT / "ai_top5_toutiao.txt"

TOUTIAO_TOP5_MARKER = "===TOUTIAO_TOP5==="

CHAT_URL = "https://api.deepseek.com/v1/chat/completions"


def _fallback_url(item: dict) -> str:
    title = (item.get("title") or "").strip()
    if not title:
        return ""
    src = item.get("source") or ""
    if "微博" in src:
        return f"https://s.weibo.com/weibo?q={quote(title)}"
    if "知乎" in src:
        return f"https://www.zhihu.com/search?q={quote(title)}&type=content"
    if "头条" in src:
        return f"https://so.toutiao.com/search?dvpf=pc&source=input&keyword={quote(title)}"
    if "抖音" in src:
        return f"https://www.douyin.com/search/{quote(title)}"
    if "腾讯" in src:
        return f"https://news.qq.com/search?query={quote(title)}"
    if "百度" in src:
        return f"https://www.baidu.com/s?wd={quote(title)}"
    if "B站" in src or "哔哩" in src:
        return f"https://search.bilibili.com/all?keyword={quote(title)}"
    return ""


def normalize_news_items(news_list: list) -> list:
    for i, x in enumerate(news_list):
        if "id" not in x:
            x["id"] = i
        u = (x.get("url") or "").strip()
        if not u:
            x["url"] = _fallback_url(x)
    return news_list


def merge_ai_tsv_to_lines(ai_text: str, news_list: list) -> str:
    """将模型输出的 id\\t摘要\\t类别 与抓取时的 url 合并为飞书用多行文本。"""
    by_id = {}
    for i, x in enumerate(news_list):
        nid = x.get("id", i)
        by_id[int(nid)] = x

    out_lines = []
    display_n = 1
    for line in ai_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            nid = int(parts[0].strip())
        except ValueError:
            continue
        summary = parts[1].strip()
        cat = parts[2].strip()
        meta = by_id.get(nid) or {}
        url = (meta.get("url") or "").strip()
        source = (meta.get("source") or "").strip()
        if source:
            # 将来源追加到同一个括号里，供飞书渲染端拆分显示来源 App。
            out_lines.append(f"{display_n}. {summary}（{cat}|{source}）")
        else:
            out_lines.append(f"{display_n}. {summary}（{cat}）")
        if url:
            out_lines.append(url)
        display_n += 1
    return "\n".join(out_lines)


def ai_output_is_id_tsv(ai_text: str) -> bool:
    for line in ai_text.strip().splitlines():
        s = line.strip()
        if not s or s == TOUTIAO_TOP5_MARKER:
            continue
        parts = s.split("\t")
        if len(parts) >= 3 and parts[0].strip().isdigit():
            return True
    return False


def split_ai_response(ai_text: str) -> tuple[str, str]:
    t = (ai_text or "").strip()
    if TOUTIAO_TOP5_MARKER in t:
        main, rest = t.split(TOUTIAO_TOP5_MARKER, 1)
        return main.strip(), rest.strip()
    return t, ""


def format_top5_for_toutiao(block: str, news_list: list) -> str:
    """解析 TOP5 区块（排名\\tid\\t切入点\\t理由），拼成可读文本并附链接。"""
    by_id = {}
    for i, x in enumerate(news_list):
        try:
            by_id[int(x.get("id", i))] = x
        except (TypeError, ValueError):
            continue
    lines_out = [
        "适合今日头条写作的 TOP5（结合大众用户偏好与推荐逻辑筛选）",
        "",
    ]
    n = 0
    for line in block.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        try:
            rank = int(parts[0].strip())
        except ValueError:
            rank = n + 1
        try:
            nid = int(parts[1].strip())
        except ValueError:
            continue
        angle = parts[2].strip()
        reason = "\t".join(parts[3:]).strip()
        meta = by_id.get(nid) or {}
        title = (meta.get("title") or "").strip()
        src = (meta.get("source") or "").strip()
        url = (meta.get("url") or "").strip()
        lines_out.append(f"{rank}. 【写作切入点】{angle or title}")
        if title:
            lines_out.append(f"   热点原文：{title}")
        if src:
            lines_out.append(f"   来源：{src}")
        lines_out.append(f"   头条推荐理由：{reason}")
        if url:
            lines_out.append(f"   {url}")
        lines_out.append("")
        n += 1
    if n == 0:
        return ""
    return "\n".join(lines_out).strip()


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
                # 只有当变量不存在或值为空时才写入，避免“环境变量已存在但为空字符串”
                # 导致后续业务把它当成缺失值而直接退出。
                if k and (k not in os.environ or not str(os.environ.get(k, "")).strip()):
                    os.environ[k] = v
    except OSError:
        pass


def ai_summary_news(news_list):
    load_dotenv_if_present()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        print(
            "请设置环境变量 DEEPSEEK_API_KEY，或在项目根目录创建 .env 写入 DEEPSEEK_API_KEY=...",
            file=sys.stderr,
        )
        sys.exit(1)

    rows = []
    for x in news_list:
        rows.append(
            {
                "id": x.get("id"),
                "title": x.get("title"),
                "url": (x.get("url") or "").strip(),
                "source": x.get("source"),
            }
        )
    content = json.dumps(rows, ensure_ascii=False)
    prompt = f"""你是中文自媒体选题编辑，供作者在「今日头条」写微头条/图文。输入为多条热点（id、title、url、source）。

【清洗与筛选】
1. 只保留适合「社会向热点」的条目：公共议题、民生、政策解读空间、科技与生活、财经现象、具有广泛讨论度的文体公共事件等；剔除硬广、引流、低俗、纯饭圈互撕、明显谣言炒作、无展开价值的碎片词。
2. 每条输出 22 字以内摘要（无信息则据标题概括），要像给作者看的「选题一句话」。
3. 类别仅限：科技/民生/娱乐/财经/社会（娱乐类仅保留仍有公共讨论面的条目）。
4. 先输出保留条目的三列表格行（制表符 Tab 分隔，不要用空格代替 Tab）：
   id<Tab>摘要<Tab>类别
   id 必须与输入一致；摘要与类别中禁止 Tab；不要表头、序号、markdown。

【今日头条 TOP5】
今日头条用户以大众、移动端为主，推荐侧重点击率、互动、停留与合规；好选题通常具备：覆盖面广、普通人有代入感、可理性展开、合规风险低、时效清晰。
请从「上面输出过的 id」中选出 5 条最适合用来写作变现与传播的，按优先级排序。

5. 在三列表格全部输出完毕后，单独起一行，必须完全一致地写：
{TOUTIAO_TOP5_MARKER}
6. 紧接着连续 5 行，每行四列 Tab 分隔（理由中禁止 Tab）：
   排名<Tab>id<Tab>写作切入点_15字内<Tab>头条推荐理由_45字内
   排名为 1-5；id 对应上文；切入点给作者可直接用作角度或标题方向。

新闻数据：
{content}
"""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }
    resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=120)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        print("DeepSeek 请求失败: ", resp.status_code, resp.text[:500], file=sys.stderr)
        raise SystemExit(1) from e
    body = resp.json()
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        print("响应结构异常: ", json.dumps(body, ensure_ascii=False)[:800], file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    if not IN_FILE.is_file():
        print("未找到 hot_news.json，请先运行 news_spider.py", file=sys.stderr)
        sys.exit(1)
    news = json.loads(IN_FILE.read_text(encoding="utf-8"))
    news = normalize_news_items(news)
    ai_raw = ai_summary_news(news)
    print("AI 精炼完成（模型原始输出）：\n", ai_raw)
    part_main, part_top5 = split_ai_response(ai_raw)
    if ai_output_is_id_tsv(part_main):
        final_text = merge_ai_tsv_to_lines(part_main, news)
        if not final_text.strip():
            print("提示：制表符合并结果为空，已回退为模型原文", file=sys.stderr)
            final_text = part_main or ai_raw
    else:
        final_text = part_main or ai_raw

    top5_block = format_top5_for_toutiao(part_top5, news)
    if top5_block:
        final_text = final_text.rstrip() + "\n\n" + top5_block
        OUT_TOP5_FILE.write_text(top5_block + "\n", encoding="utf-8")
        print("已写入：", OUT_TOP5_FILE)
    else:
        if OUT_TOP5_FILE.is_file():
            try:
                OUT_TOP5_FILE.unlink()
            except OSError:
                pass
        print("提示：未解析到 TOP5 区块，请检查模型是否按格式输出 " + TOUTIAO_TOP5_MARKER, file=sys.stderr)

    OUT_FILE.write_text(final_text, encoding="utf-8")
