# -*- coding: utf-8 -*-
"""
每日 08:00 定时触发器：常驻等待，到点后执行 run_all.py。

用法：
  cd d:\桌面\news
  python daily_trigger_8am.py

可选：
  python daily_trigger_8am.py --now   # 立即跑一次，然后继续等待下一次 08:00
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def load_dotenv_if_present():
    """把项目根目录 .env 里的变量填进当前进程环境（不存在或为空则覆盖）。"""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and (k not in os.environ or not str(os.environ.get(k, "")).strip()):
                os.environ[k] = v
    except OSError:
        pass


def next_run_time(hour: int = 8, minute: int = 0, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate


def run_all() -> int:
    """执行 run_all.py；返回退出码。"""
    r = subprocess.run(
        [PY, str(ROOT / "run_all.py")],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # 只打印末尾，避免终端刷屏
    if r.stdout:
        print("run_all.py stdout 尾部：\n" + r.stdout[-2000:])
    if r.stderr:
        print("run_all.py stderr 尾部：\n" + r.stderr[-2000:], file=sys.stderr)
    print(f"run_all.py 结束，退出码：{r.returncode}")
    return r.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="立即执行一次，然后继续等待下一次 08:00")
    args = parser.parse_args()

    load_dotenv_if_present()

    if args.now:
        run_all()

    print("每日 08:00 定时触发器已启动。按 Ctrl+C 停止。")

    while True:
        nrt = next_run_time(8, 0)
        seconds = max(0, (nrt - datetime.now()).total_seconds())
        ts = nrt.strftime("%Y-%m-%d %H:%M:%S")
        print(f"下一次执行时间：{ts}（约 {int(seconds)} 秒后）")

        # 分段睡眠，便于 Ctrl+C
        slept = 0
        while slept < seconds:
            time.sleep(min(10, seconds - slept))
            slept += min(10, seconds - slept)

        try:
            run_all()
        except Exception as e:
            print(f"执行 run_all.py 异常：{e}", file=sys.stderr)
            # 异常后仍继续等待下一次


if __name__ == "__main__":
    main()

