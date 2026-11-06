"""Docker smoke tests: API, inline/HTTP subscriptions, Clash, sing-box and reload."""
import base64
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

api = sys.argv[1].rstrip("/")
token = os.environ["API_TOKEN"]
credentials = base64.urlsafe_b64encode(b"chacha20-ietf-poly1305:smoke-password").decode().rstrip("=")
subscription = f"ss://{credentials}@example.com:443#smoke-node"


class SubscriptionHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(subscription.encode())

    def log_message(self, *_):
        pass


def get(path):
    with urlopen(api + path, timeout=10) as response:
        return response.read().decode()


for _ in range(60):
    try:
        version = get("/version")
        break
    except (URLError, TimeoutError):
        time.sleep(0.5)
else:
    raise RuntimeError(f"Server did not become ready: {api}")
assert version.startswith("subconverter ") and "backend" in version, version
assert get("/v") == version

server = ThreadingHTTPServer(("0.0.0.0", 18080), SubscriptionHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
for source in (subscription, "http://host.docker.internal:18080/subscription.txt"):
    for target in ("clash", "singbox"):
        result = get("/sub?" + urlencode({"target": target, "url": source}))
        assert "smoke-node" in result and "example.com" in result, result
        if target == "clash":
            assert "proxies:" in result and "proxy-groups:" in result and "rules:" in result, result
        else:
            outbounds = json.loads(result)["outbounds"]
            node = next(item for item in outbounds if item.get("tag") == "smoke-node")
            assert node["type"] == "shadowsocks" and node["server_port"] == 443, node
        print(f"PASS {target}: {source.split(':', 1)[0]} source")

# Reload twice: the temporary config must keep the injected administration token.
for _ in range(2):
    assert get("/readconf?" + urlencode({"token": token})).strip() == "done"
try:
    get("/readconf?token=wrong-token")
except HTTPError as error:
    assert error.code == 403, error
else:
    raise AssertionError("Administration endpoint accepted an invalid token")

server.shutdown()
server.server_close()
print(f"PASS API, aliases and token-preserving reload: {api}")
