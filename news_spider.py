# -*- coding: utf-8 -*-
"""抓取微博、知乎、头条、抖音、腾讯新闻、百度热搜、B站热搜等，统一写入 hot_news.json。"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
OUT_FILE = ROOT / "hot_news.json"


def _search_url_weibo(keyword: str) -> str:
    k = (keyword or "").strip()
    return f"https://s.weibo.com/weibo?q={quote(k)}" if k else ""


def _search_url_zhihu(keyword: str) -> str:
    k = (keyword or "").strip()
    return f"https://www.zhihu.com/search?q={quote(k)}&type=content" if k else ""


def _search_url_toutiao(keyword: str) -> str:
    k = (keyword or "").strip()
    return f"https://so.toutiao.com/search?dvpf=pc&source=input&keyword={quote(k)}" if k else ""


def _search_url_douyin(keyword: str) -> str:
    k = (keyword or "").strip()
    return f"https://www.douyin.com/search/{quote(k)}" if k else ""


def _search_url_baidu(keyword: str) -> str:
    k = (keyword or "").strip()
    return f"https://www.baidu.com/s?wd={quote(k)}" if k else ""


def _search_url_bilibili(keyword: str) -> str:
    k = (keyword or "").strip()
    return f"https://search.bilibili.com/all?keyword={quote(k)}" if k else ""


# 较新的 Chrome UA + 常见浏览器头，降低 weibo.com/ajax 被 403 的概率
def _json_utf8(res: requests.Response):
    """部分站点 response.encoding 识别不准，强制按 UTF-8 解析 JSON。"""
    return json.loads(res.content.decode("utf-8"))


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
}


def _weibo_desktop_headers():
    h = dict(HEADERS)
    h["Referer"] = "https://weibo.com/"
    h["Origin"] = "https://weibo.com"
    h["Sec-Fetch-Site"] = "same-origin"
    cookie = (os.environ.get("WEIBO_COOKIE") or "").strip()
    if cookie:
        h["Cookie"] = cookie
    return h


def _weibo_from_ajax_json(data, limit):
    hot_list = (data.get("data") or {}).get("realtime") or []
    hot_list = hot_list[:limit]
    result = []
    for item in hot_list:
        note = item.get("note") or item.get("word", "")
        if not note:
            continue
        result.append(
            {
                "title": note,
                "hot_value": item.get("num", 0),
                "source": "微博热搜",
                "url": _search_url_weibo(note),
            }
        )
    return result


def get_weibo_hot_via_m(limit: int = 10):
    """备用：移动端容器接口，部分环境下 PC ajax 403 时仍可用。"""
    url = "https://m.weibo.cn/api/container/getIndex?containerid=106003type%25"
    h = dict(HEADERS)
    h["Referer"] = "https://m.weibo.cn/"
    h["Sec-Fetch-Site"] = "same-origin"
    res = requests.get(url, headers=h, timeout=20)
    res.raise_for_status()
    body = res.json()
    result = []
    seen = set()
    for card in (body.get("data") or {}).get("cards") or []:
        for group in card.get("card_group") or []:
            title = (
                group.get("desc")
                or group.get("word_scheme")
                or group.get("title_sub")
                or group.get("word")
            )
            if not title or not str(title).strip():
                continue
            t = str(title).strip()
            if t in seen:
                continue
            seen.add(t)
            result.append(
                {
                    "title": t,
                    "hot_value": group.get("num", 0) or 0,
                    "source": "微博热搜",
                    "url": _search_url_weibo(t),
                }
            )
            if len(result) >= limit:
                return result
    return result


def get_weibo_hot(limit: int = 10):
    url = "https://weibo.com/ajax/side/hotSearch"
    try:
        res = requests.get(url, headers=_weibo_desktop_headers(), timeout=20)
        if res.status_code == 200:
            data = res.json()
            out = _weibo_from_ajax_json(data, limit)
            if out:
                return out
    except (requests.RequestException, ValueError, KeyError):
        pass

    try:
        return get_weibo_hot_via_m(limit)
    except (requests.RequestException, ValueError, KeyError) as e:
        print("微博热搜：PC 与移动端接口均不可用（{}）".format(e), file=sys.stderr)
        return []


def get_zhihu_hot(limit: int = 10):
    url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists?limit=20&desktop=true"
    h = dict(HEADERS)
    h["Referer"] = "https://www.zhihu.com/hot"
    h["Sec-Fetch-Site"] = "same-site"
    try:
        res = requests.get(url, headers=h, timeout=20)
        res.raise_for_status()
        payload = res.json()
    except (requests.RequestException, ValueError) as e:
        print("知乎热榜：", e, file=sys.stderr)
        return []
    items = payload.get("data", [])[:limit]
    result = []
    for item in items:
        target = item.get("target") or {}
        title = target.get("title")
        if not title and "title_area" in target:
            title = (target.get("title_area") or {}).get("text")
        if not title:
            q = target.get("question")
            if isinstance(q, dict):
                title = q.get("title")
        if not title:
            continue
        link = (target.get("url") or target.get("link") or "").strip()
        if not link:
            link = _search_url_zhihu(title)
        result.append(
            {
                "title": title,
                "hot_value": target.get("answer_count") or target.get("follower_count") or 0,
                "source": "知乎热榜",
                "url": link,
            }
        )
    return result


def _maybe_fix_utf8_mojibake(s: str) -> str:
    """页面里部分字段以 Latin-1 宽字节形式混入，尝试纠成 UTF-8。"""
    if not s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def get_toutiao_hot(limit: int = 10):
    """头条热点页内嵌数据，结构可能变更；失败时返回空列表。"""
    url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
    h = dict(HEADERS)
    h["Accept"] = "text/html,application/xhtml+xml,*/*"
    try:
        res = requests.get(url, headers=h, timeout=20)
        res.raise_for_status()
        enc = res.encoding
        if not enc or enc.lower() in ("iso-8859-1", "windows-1252"):
            res.encoding = getattr(res, "apparent_encoding", None) or "utf-8"
        text = res.text
    except Exception:
        return []
    # 尝试从 __INITIAL_STATE__ 或常见 JSON 片段解析标题
    titles = []
    # 模式1: "Title":"xxx"
    for m in re.finditer(r'"Title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text):
        raw = m.group(1).replace('\\"', '"')
        try:
            t = raw.encode("utf-8").decode("unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError):
            t = raw
        t = _maybe_fix_utf8_mojibake(t)
        if t and len(t) > 3 and t not in titles:
            titles.append(t)
        if len(titles) >= limit:
            break
    if not titles:
        # 模式2: abstract 热点词
        for m in re.finditer(r'"LabelName"\s*:\s*"([^"]+)"', text):
            t = m.group(1)
            if t and t not in titles:
                titles.append(t)
            if len(titles) >= limit:
                break
    return [
        {
            "title": t,
            "hot_value": 0,
            "source": "今日头条热点",
            "url": _search_url_toutiao(t),
        }
        for t in titles[:limit]
    ]


def get_douyin_hot(limit: int = 10):
    """抖音热搜榜（网页开放接口）；策略或字段变更时需更新。"""
    url = (
        "https://www.douyin.com/aweme/v1/web/hot/search/list/"
        "?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1"
    )
    h = dict(HEADERS)
    h["Referer"] = "https://www.douyin.com/"
    h["Sec-Fetch-Site"] = "same-origin"
    try:
        res = requests.get(url, headers=h, timeout=20)
        res.raise_for_status()
        body = _json_utf8(res)
    except (requests.RequestException, ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print("抖音热榜：", e, file=sys.stderr)
        return []
    words = (body.get("data") or {}).get("word_list") or (body.get("data") or {}).get(
        "trending_list"
    )
    if not words:
        return []
    result = []
    for item in words[:limit]:
        w = (item.get("word") or "").strip()
        if not w:
            continue
        result.append(
            {
                "title": w,
                "hot_value": int(item.get("hot_value") or 0),
                "source": "抖音热榜",
                "url": _search_url_douyin(w),
            }
        )
        if len(result) >= limit:
            break
    return result


def get_tencent_news_hot(limit: int = 10):
    """腾讯新闻垂直热点榜（r.inews.qq.com），过滤顶部提示条。"""
    url = "https://r.inews.qq.com/gw/event/hot_ranking_list?page_size=30&forward=1&hotType=vertical"
    h = dict(HEADERS)
    h["Referer"] = "https://news.qq.com/"
    h["Sec-Fetch-Site"] = "same-site"
    try:
        res = requests.get(url, headers=h, timeout=20)
        res.raise_for_status()
        body = _json_utf8(res)
    except (requests.RequestException, ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print("腾讯新闻热榜：", e, file=sys.stderr)
        return []
    idlist = body.get("idlist") or []
    if not idlist:
        return []
    newslist = idlist[0].get("newslist") or []
    result = []
    for item in newslist:
        if str(item.get("articletype") or "") == "560":
            continue
        tid = str(item.get("id") or "")
        if tid.startswith("TIP"):
            continue
        title = (item.get("longtitle") or item.get("title") or "").strip()
        if not title:
            continue
        hot = 0
        ev = item.get("hotEvent") or {}
        if isinstance(ev, dict):
            hot = int(ev.get("hotScore") or 0)
        if not hot:
            hot = int(item.get("readCount") or 0)
        page_url = (item.get("url") or item.get("shareUrl") or "").strip()
        if not page_url:
            aid = str(item.get("id") or "").strip()
            if aid and not aid.startswith("TIP"):
                page_url = f"https://view.inews.qq.com/a/{aid}"
        result.append(
            {
                "title": title,
                "hot_value": hot,
                "source": "腾讯新闻热点",
                "url": page_url,
            }
        )
        if len(result) >= limit:
            break
    return result


def get_baidu_hot(limit: int = 10):
    """百度实时热搜（top.baidu.com API）；结构变更时需更新解析路径。"""
    url = "https://top.baidu.com/api/board?platform=wise&tab=realtime"
    h = dict(HEADERS)
    h["Referer"] = "https://top.baidu.com/board?tab=realtime"
    h["Sec-Fetch-Site"] = "same-origin"
    try:
        res = requests.get(url, headers=h, timeout=20)
        res.raise_for_status()
        body = json.loads(res.content.decode("utf-8"))
    except (requests.RequestException, ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print("百度热搜：", e, file=sys.stderr)
        return []
    cards = (body.get("data") or {}).get("cards") or []
    flat = []
    for card in cards:
        for wrap in card.get("content") or []:
            if not isinstance(wrap, dict):
                continue
            for item in wrap.get("content") or []:
                if isinstance(item, dict):
                    flat.append(item)
    result = []
    seen = set()
    for item in flat:
        w = (item.get("word") or "").strip()
        if not w or w in seen:
            continue
        seen.add(w)
        page_url = (item.get("url") or "").strip()
        if not page_url:
            page_url = _search_url_baidu(w)
        hot = 0
        try:
            idx = item.get("index")
            if idx is not None:
                hot = int(idx)
        except (TypeError, ValueError):
            pass
        result.append(
            {
                "title": w,
                "hot_value": hot,
                "source": "百度热搜",
                "url": page_url,
            }
        )
        if len(result) >= limit:
            break
    return result


def get_bilibili_hot(limit: int = 10):
    """B 站搜索热词榜（开放接口）。"""
    url = "https://s.search.bilibili.com/main/hotword?limit=30"
    h = dict(HEADERS)
    h["Referer"] = "https://www.bilibili.com/"
    h["Sec-Fetch-Site"] = "same-site"
    try:
        res = requests.get(url, headers=h, timeout=20)
        res.raise_for_status()
        body = json.loads(res.content.decode("utf-8"))
    except (requests.RequestException, ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print("B站热搜：", e, file=sys.stderr)
        return []
    if int(body.get("code") or 0) != 0:
        return []
    words = body.get("list") or []
    result = []
    for item in words[:limit]:
        w = (item.get("show_name") or item.get("keyword") or "").strip()
        if not w:
            continue
        heat = int(item.get("heat_score") or 0)
        result.append(
            {
                "title": w,
                "hot_value": heat,
                "source": "B站热搜",
                "url": _search_url_bilibili(w),
            }
        )
        if len(result) >= limit:
            break
    return result


def collect_all():
    merged = []
    merged.extend(get_weibo_hot(10))
    merged.extend(get_zhihu_hot(10))
    merged.extend(get_toutiao_hot(10))
    merged.extend(get_douyin_hot(10))
    merged.extend(get_tencent_news_hot(10))
    merged.extend(get_baidu_hot(10))
    merged.extend(get_bilibili_hot(10))
    if not merged:
        print("未抓取到任何数据，请检查网络或接口是否变更。", file=sys.stderr)
        sys.exit(1)
    for i, x in enumerate(merged):
        x["id"] = i
    srcs = {}
    for x in merged:
        srcs[x["source"]] = srcs.get(x["source"], 0) + 1
    parts = ["{} {}".format(k, srcs[k]) for k in sorted(srcs.keys())]
    print("各源条数：" + " / ".join(parts))
    return merged


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    news = collect_all()
    print("抓取完成，共 {} 条：".format(len(news)))
    for n in news[:15]:
        print(json.dumps(n, ensure_ascii=False))
    if len(news) > 15:
        print("... 其余省略")
    OUT_FILE.write_text(
        json.dumps(news, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("已保存：", OUT_FILE)
