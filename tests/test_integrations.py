"""17.6 SOAR/ticketing entegrasyonu: JSONL ve imzalı webhook sink'leri; hata izolasyonu; runbook içerikleri."""

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ztp.detection.catalog import RUNBOOKS_DIR, load_catalog, runbook_text
from ztp.integrations import JsonlSink, WebhookSink, build_sinks


class _Receiver(BaseHTTPRequestHandler):
    received = []
    fail_first = 0

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        if _Receiver.fail_first > 0:
            _Receiver.fail_first -= 1
            self.send_response(503)
            self.end_headers()
            return
        _Receiver.received.append((dict(self.headers), body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):  # sessiz
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Receiver)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    _Receiver.received.clear()
    _Receiver.fail_first = 0
    yield f"http://127.0.0.1:{srv.server_port}/hook"
    srv.shutdown()


def test_webhook_signature_and_retry(server, monkeypatch):
    monkeypatch.setattr("ztp.integrations.time.sleep", lambda s: None)
    _Receiver.fail_first = 1  # ilk deneme 503 → yeniden dener
    sink = WebhookSink(server, secret="gizli", retries=2)
    case = {"case_id": "C-1", "kullanici": "U-1000", "risk": 80, "tespitler": [{"kural": "UEBA-0003"}]}
    assert sink.emit(case) and sink.sent == 1 and sink.errors == 0
    headers, body = _Receiver.received[-1]
    headers = {k.lower(): v for k, v in headers.items()}  # urllib başlık adlarını normalleştirir
    assert json.loads(body)["case_id"] == "C-1"
    expected = "sha256=" + hmac.new(b"gizli", body, hashlib.sha256).hexdigest()
    assert headers["x-ztp-signature"] == expected
    assert headers["content-type"] == "application/json"


def test_webhook_permanent_error_is_not_retried(server, monkeypatch):
    calls = []
    import urllib.error

    def fake_open(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr("ztp.integrations.urllib.request.urlopen", fake_open)
    sink = WebhookSink(server, retries=3)
    assert not sink.emit({"case_id": "C-2"}) and len(calls) == 1 and sink.errors == 1


def test_webhook_unreachable_counts_error(monkeypatch):
    monkeypatch.setattr("ztp.integrations.time.sleep", lambda s: None)
    sink = WebhookSink("http://127.0.0.1:9/hook", retries=1, timeout=0.2)
    assert not sink.emit({"case_id": "C-3"}) and sink.errors == 1


def test_jsonl_sink_and_builder(tmp_path, monkeypatch):
    monkeypatch.setenv("ZTP_HOOK", "s3cret")
    sinks = build_sinks(
        [{"type": "jsonl"}, {"type": "webhook", "url": "https://soar.example/x", "secret_env": "ZTP_HOOK"}], tmp_path
    )
    assert isinstance(sinks[0], JsonlSink) and isinstance(sinks[1], WebhookSink) and sinks[1].secret == "s3cret"
    sinks[0].emit({"case_id": "C-1", "kullanici": "U-1"})
    sinks[0].emit({"case_id": "C-2", "kullanici": "U-2"})
    lines = (tmp_path / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["case_id"] for line in lines] == ["C-1", "C-2"]
    with pytest.raises(ValueError):
        build_sinks([{"type": "kafka"}], tmp_path)
    with pytest.raises(ValueError):
        WebhookSink("ftp://x")


def test_every_published_rule_has_runbook_content():
    for r in load_catalog():
        if r["durum"] == "yayinda":
            txt = runbook_text(r["runbook"])
            assert txt and "İlk kontroller" in txt and "Yükseltme kriteri" in txt, r["id"]
    assert (RUNBOOKS_DIR / "RB-UEBA-0003.md").exists()
