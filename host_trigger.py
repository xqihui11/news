# -*- coding: utf-8 -*-
"""
宿主机常驻小服务：供 Docker 里的 n8n 用 HTTP 触发 run_all.py（方案一：爬虫/AI 在宿主机跑）。

启动（在项目目录）：
  python host_trigger.py

Docker 内 n8n 调用地址：
  POST http://host.docker.internal:8765/run

可选环境变量：
  HOST_TRIGGER_PORT   默认 8765
  N8N_TRIGGER_KEY     若设置则请求头需带 X-API-Key: <值>
"""
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PY = sys.executable
PORT = int(os.environ.get("HOST_TRIGGER_PORT", "8765"))
API_KEY = (os.environ.get("N8N_TRIGGER_KEY") or "").strip()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/health"):
            self._send_json(200, {"ok": True, "service": "news-host-trigger", "path": p})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        p = urlparse(self.path).path
        if p != "/run":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        if API_KEY:
            if (self.headers.get("X-API-Key") or "").strip() != API_KEY:
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
        r = subprocess.run(
            [PY, str(ROOT / "run_all.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ok = r.returncode == 0
        out = (r.stdout or "")[-8000:]
        err = (r.stderr or "")[-8000:]
        self._send_json(
            200 if ok else 500,
            {
                "ok": ok,
                "returncode": r.returncode,
                "stdout": out,
                "stderr": err,
            },
        )


def main():
    addr = ("0.0.0.0", PORT)
    httpd = HTTPServer(addr, _Handler)
    print("宿主机触发服务已启动：http://127.0.0.1:{}/run".format(PORT), file=sys.stderr)
    print("Docker 内 n8n 请请求：POST http://host.docker.internal:{}/run".format(PORT), file=sys.stderr)
    if API_KEY:
        print("已启用 X-API-Key 校验。", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。", file=sys.stderr)


if __name__ == "__main__":
    main()
