r"""The family app's database and storage, from the library machine.

Supabase's REST API with the service-role key, read from the environment at
call time - never written anywhere (AGENTS.md: secrets by symbolic name only):

    SUPABASE_URL                 https://<project>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY    the service key; bypasses RLS, so it lives in
                                 the environment of THIS machine and Vercel only

Every write is an upsert or a filtered delete, so re-running is harmless.
"""

from __future__ import annotations

import json
import os
import time


class Cloud:
    def __init__(self, url: str = "", key: str = ""):
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.url or not self.key:
            raise SystemExit("STOPPING: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY "
                             "must be set in this shell")
        import requests
        self.s = requests.Session()
        self.s.headers.update({"apikey": self.key,
                               "authorization": "Bearer " + self.key})

    def _req(self, method, path, **kw):
        # three tries with backoff: a home connection drops, a seed must not
        for attempt in range(3):
            try:
                r = self.s.request(method, self.url + path, timeout=120, **kw)
                if r.status_code < 500:
                    if r.status_code >= 400:
                        raise RuntimeError("{} {} -> {} {}".format(
                            method, path, r.status_code, r.text[:300]))
                    return r
            except OSError:
                if attempt == 2:
                    raise
            time.sleep(2 ** attempt * 2)
        raise RuntimeError("{} {} kept failing".format(method, path))

    def select(self, table: str, query: str = "") -> list:
        out, start = [], 0
        while True:
            r = self._req("GET", "/rest/v1/{}?{}".format(table, query),
                          headers={"range-unit": "items",
                                   "range": "{}-{}".format(start, start + 999)})
            page = r.json()
            out.extend(page)
            if len(page) < 1000:
                return out
            start += 1000

    def upsert(self, table: str, rows: list, on: str, chunk: int = 500) -> int:
        for i in range(0, len(rows), chunk):
            self._req("POST", "/rest/v1/{}?on_conflict={}".format(table, on),
                      data=json.dumps(rows[i:i + chunk]),
                      headers={"content-type": "application/json",
                               "prefer": "resolution=merge-duplicates,return=minimal"})
        return len(rows)

    def delete_in(self, table: str, column: str, values: list, chunk: int = 200) -> int:
        for i in range(0, len(values), chunk):
            vals = ",".join('"{}"'.format(v.replace('"', '')) for v in values[i:i + chunk])
            self._req("DELETE", "/rest/v1/{}?{}=in.({})".format(table, column, vals))
        return len(values)

    def delete_all(self, table: str, column: str) -> None:
        self._req("DELETE", "/rest/v1/{}?{}=not.is.null".format(table, column))

    def patch(self, table: str, query: str, body: dict) -> None:
        self._req("PATCH", "/rest/v1/{}?{}".format(table, query),
                  data=json.dumps(body),
                  headers={"content-type": "application/json",
                           "prefer": "return=minimal"})

    def insert(self, table: str, row: dict) -> None:
        self._req("POST", "/rest/v1/" + table, data=json.dumps(row),
                  headers={"content-type": "application/json",
                           "prefer": "return=minimal"})

    def put_object(self, key: str, body: bytes) -> None:
        self._req("POST", "/storage/v1/object/media/" + key, data=body,
                  headers={"content-type": "image/jpeg", "x-upsert": "true"})
