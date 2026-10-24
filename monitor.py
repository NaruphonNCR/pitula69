#!/usr/bin/env python3
"""Smart Topology Uptime Monitor -> MOPH Notify

ตรวจสอบสถานะเครื่องแม่ข่าย/อุปกรณ์เครือข่าย (ICMP / TCP / HTTP)
แล้วส่งแจ้งเตือน Server Down / Online ผ่าน MOPH Notify (หมอพร้อม)
ใช้แทน Uptime Kuma ได้ ไม่ต้องติดตั้งไลบรารีเพิ่ม (Python 3.8+ ล้วน)
"""

import argparse
import json
import os
import platform
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone

MOPH_NOTIFY_URL = "https://morpromt2f.moph.go.th/api/notify/send"
TH_TZ = timezone(timedelta(hours=7))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(f"[{datetime.now(TH_TZ):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_env(path):
    """อ่านไฟล์ .env แบบง่าย (KEY=VALUE) โดยไม่ทับค่าที่ตั้งไว้แล้ว"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_icmp(target, timeout):
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), target["host"]]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), target["host"]]
    start = time.monotonic()
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=timeout + 2)
    elapsed = (time.monotonic() - start) * 1000
    if result.returncode != 0:
        return False, None, "ping timeout / host unreachable"
    return True, elapsed, "ICMP reply"


def check_tcp(target, timeout):
    start = time.monotonic()
    try:
        with socket.create_connection((target["host"], int(target["port"])), timeout=timeout):
            pass
    except OSError as e:
        return False, None, f"TCP {target['port']}: {e}"
    return True, (time.monotonic() - start) * 1000, f"TCP {target['port']} open"


def check_http(target, timeout):
    url = target["url"]
    expect = target.get("expect_status", [200, 201, 202, 204, 301, 302, 303, 307, 308, 401, 403])
    if isinstance(expect, int):
        expect = [expect]
    ctx = None
    if url.startswith("https") and target.get("ignore_tls", False):
        ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, method=target.get("method", "GET"),
                                 headers={"User-Agent": "SmartTopology-Monitor/1.0"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            status = resp.status
            body = resp.read(65536).decode("utf-8", "ignore") if target.get("keyword") else ""
    except urllib.error.HTTPError as e:
        status, body = e.code, ""
    except Exception as e:  # noqa: BLE001 - รายงานทุกข้อผิดพลาดของเครือข่าย
        return False, None, f"HTTP error: {e}"
    elapsed = (time.monotonic() - start) * 1000
    if status not in expect:
        return False, elapsed, f"HTTP {status}"
    if target.get("keyword") and target["keyword"] not in body:
        return False, elapsed, f"ไม่พบคำว่า '{target['keyword']}'"
    return True, elapsed, f"HTTP {status}"


CHECKS = {"icmp": check_icmp, "ping": check_icmp, "tcp": check_tcp, "http": check_http}


def run_check(target, timeout):
    try:
        return CHECKS[target.get("type", "icmp").lower()](target, timeout)
    except subprocess.TimeoutExpired:
        return False, None, "ping timeout"
    except Exception as e:  # noqa: BLE001
        return False, None, f"error: {e}"


# ---------------------------------------------------------------------------
# MOPH Notify
# ---------------------------------------------------------------------------

def fmt_duration(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d} วัน")
    if h:
        parts.append(f"{h} ชม.")
    if m:
        parts.append(f"{m} นาที")
    if s or not parts:
        parts.append(f"{s} วินาที")
    return " ".join(parts)


def target_address(target):
    if target.get("type", "icmp").lower() == "http":
        return target["url"]
    if target.get("port"):
        return f"{target['host']}:{target['port']}"
    return target["host"]


def build_flex(target, is_up, detail, latency_ms, downtime_s, org_name):
    color = "#16A34A" if is_up else "#DC2626"
    title = "✅ ONLINE" if is_up else "🔴 SERVER DOWN"
    now = datetime.now(TH_TZ).strftime("%d/%m/%Y %H:%M:%S")

    def row(label, value):
        return {
            "type": "box", "layout": "baseline", "spacing": "sm",
            "contents": [
                {"type": "text", "text": label, "size": "sm", "color": "#6B7280", "flex": 2},
                {"type": "text", "text": str(value), "size": "sm", "color": "#111827",
                 "flex": 5, "wrap": True},
            ],
        }

    rows = [
        row("อุปกรณ์", target["name"]),
        row("ที่อยู่", target_address(target)),
        row("ประเภท", target.get("type", "icmp").upper()),
    ]
    if target.get("location"):
        rows.append(row("ตำแหน่ง", target["location"]))
    rows.append(row("รายละเอียด", detail))
    if is_up and latency_ms is not None:
        rows.append(row("Latency", f"{latency_ms:.1f} ms"))
    if is_up and downtime_s is not None:
        rows.append(row("ล่มนาน", fmt_duration(downtime_s)))
    rows.append(row("เวลา", now))

    alt = f"{title} {target['name']} ({target_address(target)})"
    return {
        "type": "flex",
        "altText": alt,
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical", "backgroundColor": color,
                "paddingAll": "14px",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "lg",
                     "color": "#FFFFFF"},
                    {"type": "text", "text": org_name, "size": "xs", "color": "#FFFFFFCC"},
                ],
            },
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": rows},
        },
    }


def send_moph_notify(message, client_key, secret_key, dry_run=False):
    payload = json.dumps({"messages": [message]}, ensure_ascii=False).encode("utf-8")
    if dry_run:
        log(f"[DRY-RUN] {message.get('altText', message.get('text'))}")
        return True
    req = urllib.request.Request(
        MOPH_NOTIFY_URL, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "client-key": client_key,
            "secret-key": secret_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log(f"MOPH Notify -> HTTP {resp.status}")
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        log(f"MOPH Notify ส่งไม่สำเร็จ HTTP {e.code}: {e.read()[:300]!r}")
    except Exception as e:  # noqa: BLE001
        log(f"MOPH Notify ส่งไม่สำเร็จ: {e}")
    return False


# ---------------------------------------------------------------------------
# Monitor loop
# ---------------------------------------------------------------------------

class TargetState:
    def __init__(self):
        self.status = None          # None = ยังไม่ทราบ, True = up, False = down
        self.fail_count = 0
        self.success_count = 0
        self.down_since = None
        self.last_reminder = None
        self.next_check = 0.0
        self.latency = None
        self.detail = ""
        self.last_check = None
        self.checks = 0
        self.ups = 0


def iso(ts):
    return ts and datetime.fromtimestamp(ts, TH_TZ).isoformat(timespec="seconds")


def build_status(targets, states, cfg):
    data = []
    for t in targets:
        st = states[t["name"]]
        data.append({
            "id": t.get("id", t["name"]),
            "name": t["name"],
            "type": t.get("type", "icmp").lower(),
            "address": target_address(t),
            "location": t.get("location", ""),
            "status": "unknown" if st.status is None else ("up" if st.status else "down"),
            "latency_ms": None if st.latency is None else round(st.latency, 2),
            "detail": st.detail,
            "last_check": iso(st.last_check),
            "down_since": iso(st.down_since),
            "uptime_percent": round(st.ups * 100 / st.checks, 2) if st.checks else None,
        })
    up = sum(1 for d in data if d["status"] == "up")
    down = sum(1 for d in data if d["status"] == "down")
    return {
        "org_name": cfg["org_name"],
        "updated": datetime.now(TH_TZ).isoformat(timespec="seconds"),
        "summary": {"total": len(data), "up": up, "down": down,
                    "availability": round(up * 100 / len(data), 1) if data else None},
        "targets": data,
    }


def save_status(path, status):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def start_http_server(port, get_status):
    """เปิด API ให้หน้า Dashboard ดึงสถานะ: GET /api/status และหน้าเว็บ GET /"""
    page_path = os.path.join(BASE_DIR, "status.html")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/api/status", "/status.json"):
                body = json.dumps(get_status(), ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            elif path in ("/", "/status.html") and os.path.exists(page_path):
                with open(page_path, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"เปิดหน้าสถานะที่ http://<ip-เครื่องนี้>:{port}/  (API: /api/status)")


def process(target, state, cfg, keys, dry_run):
    ok, latency, detail = run_check(target, cfg["timeout"])
    retries = 1 if cfg["once"] else int(target.get("retries", cfg["retries"]))
    now = time.time()
    state.last_check = now
    state.detail = detail
    state.latency = latency if ok else None
    state.checks += 1

    if ok:
        state.ups += 1
        state.fail_count = 0
        state.success_count += 1
        if state.status is False:
            downtime = now - state.down_since if state.down_since else None
            log(f"UP    {target['name']} ({detail}) หลังจากล่ม {fmt_duration(downtime or 0)}")
            send_moph_notify(build_flex(target, True, detail, latency, downtime, cfg["org_name"]),
                             *keys, dry_run=dry_run)
        elif state.status is None:
            log(f"OK    {target['name']} ({detail})")
        state.status = True
        state.down_since = None
        state.last_reminder = None
        return

    state.success_count = 0
    state.fail_count += 1
    if state.status is not False and state.fail_count >= retries:
        # ถ้าเพิ่งเริ่มโปรแกรมแล้วล่มอยู่แล้ว ก็แจ้งด้วย (notify_on_start)
        first_run = state.status is None
        state.status = False
        state.down_since = now
        state.last_reminder = now
        log(f"DOWN  {target['name']} ({detail})")
        if not first_run or cfg["notify_on_start"]:
            send_moph_notify(build_flex(target, False, detail, None, None, cfg["org_name"]),
                             *keys, dry_run=dry_run)
    elif state.status is False and cfg["reminder_minutes"] > 0:
        if now - state.last_reminder >= cfg["reminder_minutes"] * 60:
            state.last_reminder = now
            detail = f"{detail} (ยังล่มอยู่ {fmt_duration(now - state.down_since)})"
            log(f"STILL DOWN {target['name']}")
            send_moph_notify(build_flex(target, False, detail, None, None, cfg["org_name"]),
                             *keys, dry_run=dry_run)
    elif state.status is not False:
        log(f"WARN  {target['name']} ล้มเหลว {state.fail_count}/{retries} ({detail})")


def main():
    parser = argparse.ArgumentParser(description="Uptime monitor -> MOPH Notify")
    parser.add_argument("-c", "--config", default=os.path.join(BASE_DIR, "config.json"))
    parser.add_argument("--dry-run", action="store_true", help="ไม่ส่งจริง แค่แสดงผลบนจอ")
    parser.add_argument("--once", action="store_true", help="ตรวจรอบเดียวแล้วจบ")
    parser.add_argument("--test-notify", action="store_true", help="ส่งข้อความทดสอบ แล้วจบ")
    args = parser.parse_args()

    load_env(os.path.join(BASE_DIR, ".env"))
    client_key = os.environ.get("MOPH_CLIENT_KEY", "")
    secret_key = os.environ.get("MOPH_SECRET_KEY", "")
    if not args.dry_run and not (client_key and secret_key):
        sys.exit("กรุณาตั้งค่า MOPH_CLIENT_KEY และ MOPH_SECRET_KEY ในไฟล์ .env")
    keys = (client_key, secret_key)

    with open(args.config, encoding="utf-8") as f:
        raw = json.load(f)
    cfg = {
        "interval": raw.get("interval_seconds", 60),
        "timeout": raw.get("timeout_seconds", 5),
        "retries": raw.get("retries", 3),
        "reminder_minutes": raw.get("reminder_minutes", 0),
        "notify_on_start": raw.get("notify_on_start", True),
        "org_name": raw.get("org_name", "Smart Topology NOC"),
        "status_file": raw.get("status_file", ""),
        "http_port": int(raw.get("http_port", 0)),
        "once": args.once,
    }
    targets = [t for t in raw["targets"] if t.get("enabled", True)]

    if args.test_notify:
        ok = send_moph_notify({"type": "text",
                               "text": f"🔔 ทดสอบระบบแจ้งเตือน {cfg['org_name']} ทำงานปกติ"},
                              *keys, dry_run=args.dry_run)
        sys.exit(0 if ok else 1)

    states = {t["name"]: TargetState() for t in targets}
    log(f"เริ่มตรวจสอบ {len(targets)} อุปกรณ์ ทุก {cfg['interval']} วินาที"
        f"{' (DRY-RUN)' if args.dry_run else ''}")
    if cfg["http_port"] and not args.once:
        start_http_server(cfg["http_port"], lambda: build_status(targets, states, cfg))

    with ThreadPoolExecutor(max_workers=min(32, max(1, len(targets)))) as pool:
        while True:
            now = time.monotonic()
            due = [t for t in targets if states[t["name"]].next_check <= now]
            for t in due:
                states[t["name"]].next_check = now + t.get("interval_seconds", cfg["interval"])
            list(pool.map(lambda t: process(t, states[t["name"]], cfg, keys, args.dry_run), due))
            if cfg["status_file"]:
                save_status(os.path.join(BASE_DIR, cfg["status_file"]),
                            build_status(targets, states, cfg))
            if args.once:
                break
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("หยุดการทำงาน")
