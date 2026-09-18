"""Vaka çıkış entegrasyonları — 17.6: sistem çıktısı bağımsız bir panel değil, mevcut SOAR / ticketing altyapısına akar.

Çıkışa yalnızca takma adlı vaka gider (gerçek kimlik yok — 20.1/20.3). Her sink bağımsızdır: biri düşerse diğerleri ve
dosya çıktıları etkilenmez; hata sayacı sağlık raporuna girer. Webhook gövdesi HMAC-SHA256 ile imzalanır ki alıcı
(SOAR) kaynağı doğrulayabilsin; sır ortam değişkeninden okunur, yapılandırma dosyasına yazılmaz.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence

LOG = logging.getLogger(__name__)


def _json_default(o: Any) -> Any:
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    return str(o)


class CaseSink(Protocol):
    name: str

    def emit(self, case: dict) -> bool: ...


class JsonlSink:
    """Satır başına bir vaka (JSON Lines) — log toplayıcı / SIEM alımı için en basit bağlayıcı."""

    def __init__(self, path: Path):
        self.name = f"jsonl:{path.name}"
        self.path = Path(path)
        self.errors = 0

    def emit(self, case: dict) -> bool:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(case, ensure_ascii=False, default=_json_default) + "\n")
            return True
        except OSError as exc:
            self.errors += 1
            LOG.error("JSONL sink yazılamadı (%s): %s", self.path, exc)
            return False


class WebhookSink:
    """HTTP POST (JSON) + `X-ZTP-Signature: sha256=<hmac>` başlığı; geçici hatalarda üstel geri çekilmeli yeniden deneme."""

    def __init__(
        self,
        url: str,
        secret: Optional[str] = None,
        timeout: float = 10.0,
        retries: int = 3,
        headers: Optional[Dict[str, str]] = None,
        name: str = "webhook",
    ):
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("Webhook URL http(s) olmalı")
        self.name = f"{name}:{url}"
        self.url, self.secret, self.timeout, self.retries = url, secret, timeout, max(0, retries)
        self.headers = dict(headers or {})
        self.errors = 0
        self.sent = 0

    def _sign(self, body: bytes) -> Optional[str]:
        if not self.secret:
            return None
        return "sha256=" + hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()

    def emit(self, case: dict) -> bool:
        body = json.dumps(case, ensure_ascii=False, default=_json_default).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "ztp/0.1", **self.headers}
        sig = self._sign(body)
        if sig:
            headers["X-ZTP-Signature"] = sig
        delay = 0.5
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    if 200 <= r.status < 300:
                        self.sent += 1
                        return True
                    LOG.warning("Webhook %s: HTTP %s", self.url, r.status)
            except urllib.error.HTTPError as exc:
                if 400 <= exc.code < 500 and exc.code != 429:  # kalıcı hata: yeniden deneme anlamsız
                    LOG.error("Webhook %s reddetti (HTTP %s)", self.url, exc.code)
                    self.errors += 1
                    return False
                LOG.warning("Webhook %s geçici hata (HTTP %s), deneme %d", self.url, exc.code, attempt + 1)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                LOG.warning("Webhook %s erişilemedi (%s), deneme %d", self.url, exc, attempt + 1)
            if attempt < self.retries:
                time.sleep(delay)
                delay *= 2
        self.errors += 1
        return False


def build_sinks(specs: Sequence[dict], out_dir: Path) -> List[CaseSink]:
    """Yapılandırmadan sink listesi. Örnek:
    sinks:
      - type: jsonl
      - type: webhook
        url: https://soar.example/api/ztp
        secret_env: ZTP_WEBHOOK_SECRET
        headers: {Authorization: "Bearer ..."}   # tercihen ortam değişkeninden
    """
    sinks: List[CaseSink] = []
    for spec in specs or []:
        kind = str(spec.get("type", "")).lower()
        if kind == "jsonl":
            sinks.append(JsonlSink(out_dir / spec.get("path", "cases.jsonl")))
        elif kind == "webhook":
            secret = os.environ.get(spec["secret_env"]) if spec.get("secret_env") else spec.get("secret")
            if spec.get("secret_env") and not secret:
                LOG.warning("Webhook sırrı ortamda yok (%s); imzasız gönderilecek", spec["secret_env"])
            sinks.append(
                WebhookSink(
                    spec["url"],
                    secret=secret,
                    timeout=float(spec.get("timeout", 10)),
                    retries=int(spec.get("retries", 3)),
                    headers=spec.get("headers"),
                    name=spec.get("name", "webhook"),
                )
            )
        else:
            raise ValueError(f"Bilinmeyen sink türü: {kind!r} (jsonl | webhook)")
    return sinks
