"""Read-only production availability checks; never changes business records."""
import json
import time
import urllib.error
import urllib.request

BASE = "https://yifunlife-workplace.yifunlife.workers.dev"
def check():
    for path, expected in [("/", 200), ("/api/auth/session", 200), ("/sales-dashboard.css", 200), ("/api/projects", 401), ("/modules/quote/", 401), ("/internal/", 404)]:
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
        try:
            response = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            assert response.code == expected, f"{path}: expected {expected}, got {response.code}"
            if path == "/api/auth/session":
                assert json.loads(body)["authenticated"] is False
            if expected == 200:
                assert len(body) > 0
            print(path, response.code, flush=True)

if __name__ == "__main__":
    for attempt in range(12):
        try:
            check()
            break
        except (AssertionError, urllib.error.URLError, TimeoutError):
            if attempt == 11:
                raise
            time.sleep(10)
