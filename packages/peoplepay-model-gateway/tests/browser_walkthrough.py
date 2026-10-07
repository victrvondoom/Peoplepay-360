"""Browser walkthrough (not collected by pytest). Usage:
    python browser_walkthrough.py http://127.0.0.1:8099 /path/to/screenshots
Needs a running gateway started with PEOPLEPAY_MODELS_ENABLE_MOCK=1 and Playwright + Chromium.
A stub OpenAI-compatible server on loopback plays the part of "the user's own endpoint": it is OUR server, so the result
is MOCK VERIFIED, not live-provider verified."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path.endswith("/models"):
            return self._send(200, {"data": [{"id": "stub-a"}, {"id": "stub-b"}, {"id": "stub-limited"}]})
        self._send(404, {})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        model = body.get("model")
        if model == "stub-limited":
            return self._send(429, {"error": {"message": "rate limit reached"}})
        words = f"[{model}] reply".split(" ")
        if body.get("stream"):
            chunks = "".join("data: " + json.dumps({"model": model, "choices": [{"delta": {"content": w + " "}}]}) + "\n\n" for w in words)
            chunks += "data: " + json.dumps({"model": model, "choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}) + "\n\ndata: [DONE]\n\n"
            return self._send(200, chunks.encode(), "text/event-stream")
        self._send(200, {"model": model, "choices": [{"message": {"content": " ".join(words)}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
stub_url = f"http://127.0.0.1:{srv.server_address[1]}/v1"

def pick(page, term):
    """Open the selector, expand the full browser if it is collapsed, search, choose."""
    page.click(".pp-sel-btn")
    page.wait_for_selector(".pp-panel:not([hidden])")
    if page.locator(".pp-panel >> text=More models").count():
        page.click(".pp-panel >> text=More models")
    page.fill(".pp-panel input[type=search]", term)
    page.click(f".pp-panel button.pp-opt:has-text('{term}')")


with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"]) \
        if __import__("os").path.exists("/opt/pw-browsers/chromium-1194/chrome-linux/chrome") else p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    problems = []
    page.on("console", lambda m: problems.append(m.text) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: problems.append(str(e)))

    # 1. Selector shows Auto, existing providers appear
    page.goto(f"{BASE}/ask")
    page.wait_for_selector(".pp-sel-btn")
    check("selector shows Auto by default", "Auto" in page.inner_text(".pp-sel-label"))
    page.goto(f"{BASE}/models")
    page.wait_for_selector("#conn-cards .pp-card")
    check("existing (environment) providers appear", page.locator("#conn-cards .pp-card").count() >= 2)
    check("system connections show Connected", "Connected" in page.inner_text("#conn-cards"))
    page.screenshot(path=f"{OUT}/01-settings-providers.png", full_page=True)

    # 2. BYOK: connect a custom endpoint through the form
    page.click("#add-provider summary")
    page.select_option("#ptype", "openai_compatible")
    page.fill("#pname", "My stub endpoint")
    page.fill("#pf-base_url", stub_url)
    page.fill("#pf-api_key", "sk-WALKTHROUGH-SECRET-0123456789")
    page.select_option("#pf-privacy", "organization")
    page.check("#pack")
    page.click("#add-form button[type=submit]")
    page.wait_for_selector("text=3 models found", timeout=10000)
    check("connect + test reports models found", True)
    check("api key field cleared after submit", page.input_value("#pf-api_key") == "")
    check("secret never rendered in the page", "WALKTHROUGH-SECRET" not in page.content())
    page.wait_for_selector("#conn-cards .pp-card >> text=My stub endpoint")
    page.screenshot(path=f"{OUT}/02-after-connect.png", full_page=True)

    # 3. Ask using a chosen model, then switch mid-conversation
    page.goto(f"{BASE}/ask")
    page.click(".pp-sel-btn")
    page.wait_for_selector(".pp-panel:not([hidden])")
    page.screenshot(path=f"{OUT}/03-selector-open.png")
    page.click("text=More models")
    page.fill(".pp-panel input[type=search]", "stub-a")
    page.click(".pp-panel button.pp-opt:has-text('stub-a')")
    check("status says future replies use stub-a", "stub-a" in page.inner_text("#status"))
    page.fill("#text", "hello from the walkthrough")
    page.click("#send")
    page.wait_for_selector(".pp-msg:not(.user) .pp-meta", timeout=10000)
    first = page.inner_text(".pp-msg:not(.user)")
    check("first reply came from stub-a with route metadata", "[stub-a]" in first and "stub-a" in first.split("\n")[-1])
    pick(page, "stub-b")
    page.fill("#text", "and now a second message"); page.click("#send")
    page.locator(".pp-msg:not(.user) .pp-meta").nth(1).wait_for(timeout=10000)
    msgs = page.locator(".pp-msg:not(.user)").all_inner_texts()
    check("second reply came from stub-b, first message intact", "[stub-b]" in msgs[1] and "[stub-a]" in msgs[0] and page.locator(".pp-msg.user").count() == 2)
    page.screenshot(path=f"{OUT}/04-switched-conversation.png", full_page=True)

    # 4. Rate-limited primary -> visible fallback
    pick(page, "stub-limited")
    page.fill("#text", "this should fall back"); page.click("#send")
    page.locator(".pp-msg:not(.user) .pp-meta").nth(2).wait_for(timeout=10000)
    third = page.locator(".pp-msg:not(.user)").all_inner_texts()[2]
    check("429 primary fell back with a visible, subtle notice", "switched provider" in third and "rate limited" in third.lower())
    page.screenshot(path=f"{OUT}/05-fallback.png", full_page=True)

    # 5. Developer mode details
    page.check("#dev", force=True) if page.locator("#dev").is_visible() else (page.click("summary:has-text('Request options')"), page.check("#dev"))
    page.fill("#text", "show me why"); page.click("#send")
    page.wait_for_selector(".pp-dev", timeout=10000)
    check("developer mode shows 'Why this model?'", "Why this model?" in page.inner_text(".pp-dev"))
    page.screenshot(path=f"{OUT}/06-developer-mode.png", full_page=True)

    # 6. Local only
    page.click("#new")
    page.check("#local-only")
    page.wait_for_selector("#status:has-text('Local only is on')")
    page.click(".pp-sel-btn"); page.click(".pp-panel [role=listbox] >> nth=0 >> button.pp-opt:has-text('Auto')")
    page.fill("#text", "private question"); page.click("#send")
    page.wait_for_selector(".pp-msg:not(.user) .pp-meta", timeout=10000)
    local_reply = page.locator(".pp-msg:not(.user)").last.inner_text()
    check("local-only answered by a local route", "Local (mock)" in local_reply, local_reply.split("\n")[-1])
    page.screenshot(path=f"{OUT}/07-local-only.png", full_page=True)
    page.uncheck("#local-only")

    # 7. Keyboard accessibility of the selector
    page.goto(f"{BASE}/ask"); page.wait_for_selector(".pp-sel-btn")
    page.focus(".pp-sel-btn"); page.keyboard.press("Enter")
    page.wait_for_selector(".pp-panel button.pp-opt")
    focused = page.evaluate("document.activeElement.className")
    check("opening with Enter moves focus into the options", "pp-opt" in focused, focused)
    page.keyboard.press("ArrowDown")
    check("arrow keys move between options", page.evaluate("document.activeElement.className").find("pp-opt") >= 0)
    page.keyboard.press("Escape")
    check("Escape closes the panel and returns focus to the button", page.locator(".pp-panel").is_hidden() and "pp-sel-btn" in page.evaluate("document.activeElement.className"))
    check("selector has an accessible name", "Intelligence" in (page.get_attribute(".pp-sel-btn", "aria-label") or ""))

    # 8. 390px responsive
    m = br.new_context(viewport={"width": 390, "height": 844}); mp = m.new_page()
    mp.on("pageerror", lambda e: problems.append(str(e)))
    for path in ("/ask", "/models"):
        mp.goto(f"{BASE}{path}"); mp.wait_for_timeout(600)
        sw = mp.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        check(f"390px {path}: no horizontal page scroll", sw[0] <= sw[1], str(sw))
    mp.goto(f"{BASE}/ask"); mp.click(".pp-sel-btn"); mp.wait_for_selector(".pp-panel:not([hidden])")
    mp.click("text=More models"); mp.wait_for_timeout(300)
    box = mp.locator(".pp-panel").bounding_box()
    check("390px selector panel stays inside the viewport", box["x"] >= 0 and box["x"] + box["width"] <= 390.5 and box["y"] >= 0 and box["y"] + box["height"] <= 844.5, str(box))
    mp.screenshot(path=f"{OUT}/08-mobile-selector.png")
    mp.keyboard.press("Escape")
    mp.goto(f"{BASE}/models"); mp.wait_for_selector("#conn-cards .pp-card")
    mp.screenshot(path=f"{OUT}/09-mobile-settings.png", full_page=True)

    csp = [x for x in problems if "Content Security Policy" in x or "Refused" in x]
    check("no CSP violations or page errors", not csp and not [x for x in problems if "pageerror" in x.lower()], "; ".join(problems[:3]))
    br.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
