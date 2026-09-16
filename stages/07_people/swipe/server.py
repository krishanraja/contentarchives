r"""The swipe game: a phone-friendly way to answer what a machine cannot.

WHAT IT IS FOR

Metadata gets you when, where, which device and which folder. A vision model
gets you kind, subject and how many faces. Neither gets you WHO - and who is
the thing people actually search by. Only a human knows that the child in the
green dinosaur pyjamas is your nephew, and only your mother can identify the
people in a photograph from 2008.

So this asks one question at a time, on a phone, with a big picture and two
buttons. It is designed to be played in a queue or on a sofa, by anyone in the
family, for as long as they feel like - and to be worth something after ten
answers, not only after ten thousand.

WHY IT RUNS LOCALLY AND WILL NOT BE PUBLISHED

It serves photographs of a family and, in the people table, the identities of
minors and relatives. The standing decision on this project is that the
per-file map never leaves the machine. So: a LAN server, reachable from a phone
on the same wifi, and nothing is uploaded anywhere. Point a browser at
http://<this-machine>:8420 and it works; expose it to the internet and you have
published your family album.

WHAT IT ASKS, IN ORDER OF VALUE PER TAP

  1. merge   - "same person?" Two faces, one tap. One answer can collapse
               hundreds of observations, so it is asked first.
  2. name    - "who is this?" Turns Person 142 into someone real, and
               propagates to every observation already attached to that id.
  3. keep    - "memory, or clutter?" The residue vision was unsure about.

Every answer is written as source=human, confidence=1.0, which outranks any
model claim for the same tag forever after. Nothing is overwritten: the model's
guess stays in the store as history.

    python server.py --store D:\_PhotoAudit\enrichment --thumbs D:\_thumbs
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import random
import socket
import socketserver
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from store import Store                                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STORE: Store
THUMBS: str


def _thumb_path(h: str) -> str:
    return os.path.join(THUMBS, h[:2], h + ".jpg")


def next_question() -> dict:
    """Highest value per tap, cheapest question first."""
    # 1. an unresolved merge suggestion
    merges = [r for r in STORE._read("merge_suggestions.csv")
              if r["status"] == "pending"]
    if merges:
        m = merges[0]
        a_obs = [r for r in STORE._read("observations.csv")
                 if r["person_id"] == m["person_a"]]
        b_obs = [r for r in STORE._read("observations.csv")
                 if r["person_id"] == m["person_b"]]
        if a_obs and b_obs:
            return {"type": "merge", "a": m["person_a"], "b": m["person_b"],
                    "reason": m["reason"],
                    "a_hash": a_obs[0]["hash"], "b_hash": b_obs[0]["hash"]}

    # 2. an unnamed person with the most observations - naming it pays most
    obs = STORE._read("observations.csv")
    counts: dict[str, int] = {}
    for r in obs:
        counts[r["person_id"]] = counts.get(r["person_id"], 0) + 1
    unnamed = [p for p in STORE.people() if not p["name"]]
    unnamed.sort(key=lambda p: -counts.get(p["person_id"], 0))
    if unnamed:
        p = unnamed[0]
        mine = [r for r in obs if r["person_id"] == p["person_id"]]
        if mine:
            return {"type": "name", "person_id": p["person_id"],
                    "label": p["display_label"],
                    "count": counts.get(p["person_id"], 0),
                    "hashes": [r["hash"] for r in mine[:6]]}

    # 3. a file the model was unsure about
    low = [r for r in STORE._read("content_tags.csv")
           if r["tag"] == "keep" and r["source"].startswith("model")
           and float(r["confidence"] or 1) < 0.75]
    if low:
        r = random.choice(low)
        t = STORE.tags_for(r["hash"])
        return {"type": "keep", "hash": r["hash"],
                "guess": t.get("kind", ("?",))[0],
                "subject": t.get("subject", ("",))[0]}

    return {"type": "done"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/next":
            return self._send(200, json.dumps(next_question()).encode(),
                              "application/json")
        if u.path.startswith("/thumb/"):
            h = u.path.split("/")[-1]
            p = _thumb_path(h)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    return self._send(200, f.read(), "image/jpeg")
            return self._send(404, b"no thumb", "text/plain")
        if u.path == "/stats":
            people = STORE.people()
            return self._send(200, json.dumps({
                "people": len(people),
                "named": sum(1 for p in people if p["name"]),
                "observations": len(STORE._read("observations.csv")),
                "tagged": len(STORE.known_hashes()),
            }).encode(), "application/json")
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n) or b"{}")
        t = d.get("type")
        if t == "merge":
            STORE.resolve_merge(int(d["a"]), int(d["b"]), bool(d["accept"]))
        elif t == "name":
            if d.get("name"):
                STORE.name_person(int(d["person_id"]), d["name"].strip())
        elif t == "keep":
            STORE.tag(d["hash"], "keep", "yes" if d["keep"] else "no",
                      source="human", confidence=1.0)
        return self._send(200, b'{"ok":true}', "application/json")

    def log_message(self, *a):     # quiet: this runs on someone's sofa
        pass


def main() -> None:
    global STORE, THUMBS
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--thumbs", required=True)
    ap.add_argument("--port", type=int, default=8420)
    a = ap.parse_args()
    STORE = Store(a.store)
    THUMBS = a.thumbs

    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print(f"swipe game on http://{ip}:{a.port}  (open this on your phone)")
    print("LAN only. Do not port-forward this - it serves your family album.")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", a.port), Handler) as srv:
        srv.serve_forever()


if __name__ == "__main__":
    main()
