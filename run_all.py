# -*- coding: utf-8 -*-
"""一键执行：抓取 -> AI 精炼 -> 飞书推送。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def run_step(name: str, script: str) -> None:
    print(f"\n===== {name} =====")
    r = subprocess.run(
        [PY, str(ROOT / script)],
        cwd=str(ROOT),
        check=False,
    )
    if r.returncode != 0:
        print(f"步骤失败: {script}，退出码 {r.returncode}", file=sys.stderr)
        sys.exit(r.returncode)


if __name__ == "__main__":
    run_step("1. 抓取热点新闻", "news_spider.py")
    run_step("2. AI 智能筛选摘要分类", "ai_news_filter.py")
    run_step("3. 推送至飞书", "send_to_feishu.py")
    print("\n全流程执行完毕。")
