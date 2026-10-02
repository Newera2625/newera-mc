#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Newera MC runner 进程控制代理
监听 127.0.0.1:12502（经 SSH 反向隧道暴露给 VPS 面板），提供：
  GET  /api/server/status   -> {"running": bool, "pid": int}
  POST /api/server/start    -> 拉起 run.sh（nohup）
  POST /api/server/stop     -> RCON stop，兜底 pkill
鉴权：X-Auth-Token 请求头（须与面板配置一致）
"""
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = int(os.environ.get("MC_AGENT_PORT", "12502"))
TOKEN = os.environ.get("MC_AGENT_TOKEN", "xqn-mc-admin-2026-token")
WORKDIR = os.environ.get("MC_WORKDIR", os.getcwd())
RCON_PORT = int(os.environ.get("MC_RCON_PORT", "25575"))
RCON_PASS = os.environ.get("MC_RCON_PASS", "newera2625")

LOCK = threading.Lock()


def server_proc():
    """返回 MC 服务器 java 进程（兼容 NeoForge/vanilla 多种启动命令行）"""
    patterns = [
        "java.*server\\.jar",
        "java.*neoforge",
        "java.*unix_args",
        "java.*user_jvm_args",
    ]
    found = set()
    try:
        for pat in patterns:
            out = subprocess.run(
                ["pgrep", "-f", pat],
                capture_output=True, text=True, timeout=5,
            ).stdout.split()
            found.update(int(p) for p in out)
    except Exception:
        pass
    me = os.getpid()
    return [p for p in sorted(found) if p != me]


def _probe_port(port, timeout=1.0):
    """探测本机端口是否有服务监听"""
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def running():
    procs = server_proc()
    if procs:
        return True, procs[0]
    # 兜底：模组管理 API 端口（12501）活着则视为服务器在运行
    if _probe_port(12501):
        return True, 0
    return False, 0


def rcon(command, timeout=8):
    """RCON 客户端（与 mc-ops.sh 同协议）"""
    try:
        s = socket.create_connection(("127.0.0.1", RCON_PORT), timeout=5)

        def packet(rid, ptype, body):
            data = struct.pack("<III", rid, ptype, len(body.encode()) + 2) + body.encode() + b"\x00\x00"
            s.sendall(data)

        def read_pkt():
            size = struct.unpack("<I", s.recv(4))[0]
            rid, ptype = struct.unpack("<II", s.recv(8))
            body = s.recv(size - 10).decode(errors="replace")
            return body

        packet(1, 3, RCON_PASS)
        read_pkt()
        packet(2, 2, command)
        out = read_pkt()
        s.close()
        return out.strip()
    except Exception as e:
        return f"rcon error: {e}"


class Handler(BaseHTTPRequestHandler):
    def _auth(self):
        if self.headers.get("X-Auth-Token") != TOKEN:
            self._json(401, {"ok": False, "result": "bad token"})
            return False
        return True

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/api/server/status":
            if not self._auth():
                return
            run, pid = running()
            self._json(200, {"ok": True, "running": run, "pid": pid})
            return
        self._json(404, {"ok": False, "result": "not found"})

    def do_POST(self):
        if not self._auth():
            return
        body = self._body()
        if self.path == "/api/server/start":
            with LOCK:
                run, pid = running()
                if run:
                    self._json(200, {"ok": True, "result": "already running", "pid": pid})
                    return
                log = open(os.path.join(WORKDIR, "console.log"), "a")
                p = subprocess.Popen(
                    ["bash", "start.sh"],
                    cwd=WORKDIR, stdout=log, stderr=log,
                    start_new_session=True,
                )
            self._json(200, {"ok": True, "result": "started", "pid": p.pid})
            return
        if self.path == "/api/server/stop":
            with LOCK:
                out = rcon("stop")
                time.sleep(3)
                procs = server_proc()
                for p in procs:
                    try:
                        os.kill(p, signal.SIGTERM)
                    except Exception:
                        pass
            self._json(200, {"ok": True, "result": "stop issued", "rcon": out})
            return
        self._json(404, {"ok": False, "result": "not found"})


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[mc-agent] listening on {HOST}:{PORT}, workdir={WORKDIR}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
