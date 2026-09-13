"""只用 HTTP(公开 t.me 预览页)探测频道/群的订阅数与最近更新,用于分析前的门槛过滤。
不使用 telethon、不登录。可断点续跑。全局限速(令牌桶,默认 ~5 req/s),小并发抵消网络延迟。

    python scripts/tg_http_peek.py <candidates.tsv> <out.csv> [rps] [workers]

candidates.tsv 每行: <username>\t<source_tags>
out.csv 列: username,source,kind,count,last_date,days_ago,n_posts,err
"""
from __future__ import annotations
import csv, re, sys, time, threading, queue
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

IN = Path(sys.argv[1])
OUT = Path(sys.argv[2])
RPS = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
WORKERS = int(sys.argv[4]) if len(sys.argv) > 4 else 5
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
now = datetime.now(timezone.utc)

_lock = threading.Lock()
_next = [0.0]


def throttle():
    with _lock:
        t = time.monotonic()
        wait = max(0.0, _next[0] - t)
        _next[0] = max(t, _next[0]) + 1.0 / RPS
    if wait > 0:
        time.sleep(wait)


def get(url):
    throttle()
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def num(s):
    d = re.sub(r"[^0-9]", "", s or "")
    return int(d) if d else None


def parse_count(html):
    for m in re.finditer(
        r'counter_value"[^>]*>([\d   ,]+)</span>\s*'
        r'<span class="counter_type">(\w+)', html):
        if m.group(2) in ("subscribers", "members"):
            return num(m.group(1)), ("channel" if m.group(2) == "subscribers" else "group")
    m = re.search(r'tgme_page_extra">([^<]+)</div>', html)
    if m:
        t = m.group(1)
        if "subscriber" in t:
            return num(t.split("subscriber")[0]), "channel"
        if "member" in t:
            return num(t.split("member")[0]), "group"
    return None, "unknown"


def parse_last(html):
    ts = re.findall(r'<time datetime="([^"]+)"', html)
    best = None
    for t in ts:
        try:
            d = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)
            if best is None or d > best:
                best = d
        except Exception:
            pass
    return best, len(ts)


def probe(u):
    count = None
    kind = "unknown"
    last = None
    nposts = 0
    err = ""
    try:
        html = get(f"https://t.me/s/{u}")
        count, kind = parse_count(html)
        last, nposts = parse_last(html)
        if count is None:
            html2 = get(f"https://t.me/{u}")
            count, kind = parse_count(html2)
    except HTTPError as e:
        err = f"http{e.code}"
    except URLError:
        err = "urlerr"
    except Exception as e:
        err = type(e).__name__
    days = (now - last).days if last else ""
    return [u, kind, count if count is not None else "",
            last.isoformat() if last else "", days, nposts, err]


def main():
    cands = []
    for line in IN.read_text(encoding="utf-8").splitlines():
        if line.strip():
            p = line.split("\t")
            cands.append((p[0], p[1] if len(p) > 1 else ""))
    done = set()
    if OUT.exists():
        done = {r[0] for r in csv.reader(OUT.open(encoding="utf-8")) if r}
    todo = [c for c in cands if c[0] not in done]
    print(f"共 {len(cands)}，已完成 {len(done)}，本次 {len(todo)}，rps={RPS} workers={WORKERS}", flush=True)
    src = {u: s for u, s in cands}
    new = not OUT.exists()
    f = OUT.open("a", encoding="utf-8", newline="")
    w = csv.writer(f)
    if new:
        w.writerow(["username", "source", "kind", "count", "last_date", "days_ago", "n_posts", "err"])
    wlock = threading.Lock()
    q = queue.Queue()
    for u, _ in todo:
        q.put(u)
    cnt = [0]

    def worker():
        while True:
            try:
                u = q.get_nowait()
            except queue.Empty:
                return
            row = probe(u)
            with wlock:
                w.writerow([row[0], src.get(row[0], "")] + row[1:])
                f.flush()
                cnt[0] += 1
                if cnt[0] % 50 == 0:
                    print(f"  {cnt[0]}/{len(todo)}", flush=True)

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    f.close()
    print("done", flush=True)


main()
