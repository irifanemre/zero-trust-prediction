"""LLM raporlama — 15.2/15.3: yalnızca inceleme kuyruğu için, kanıta bağlı, çıktı doğrulamalı; skorlamada yer almaz."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import List, Tuple

from ztp.config import TenantConfig
from ztp.reporting.template import deterministic_summary

LOG = logging.getLogger(__name__)


class LLMReporter:
    SYSTEM = (
        "Sen bir SOC raporlama yardımcısısın. Yalnızca verilen KANIT listesindeki olayları ve sayıları kullan. "
        "Her cümlenin sonunda köşeli parantez içinde dayandığı olay kimliklerini yaz, örn. [E-0001a2f]. "
        "Kanıtta olmayan hiçbir varlık adı, teknik, sayı veya niyet yorumu üretme. Kişinin niyeti/karakteri hakkında "
        "yargı yazma; yalnızca gözlemlenen davranışı özetle. Kullanıcı adları takma addır (U-xxxx); gerçek kimlik tahmini "
        "yapma. Türkçe, 3–6 cümle, düz metin."
    )

    def __init__(self, cfg: TenantConfig):
        self.cfg = cfg
        self.calls = 0
        self.tokens = 0

    def summarize(self, case: dict) -> Tuple[str, str]:
        """Döndürür (özet, kaynak). Kanıta bağlılık + çıktı doğrulaması; başarısızlıkta şablon (15.3)."""
        fallback = deterministic_summary(case)
        if self.cfg.llm_backend == "none":
            return fallback, "sablon"
        prompt = self._prompt(case)
        try:
            text = self._ollama(prompt) if self.cfg.llm_backend == "ollama" else self._anthropic(prompt)
        except Exception as exc:
            LOG.warning("LLM erişilemedi/hata (%s) — şablon rapora düşüldü", exc)
            return fallback, f"sablon (LLM hatası: {type(exc).__name__})"
        ok, problems = self._validate(text, case)
        if not ok:
            LOG.warning("LLM çıktısı doğrulanamadı: %s — şablon rapora düşüldü", problems)
            return fallback, f"sablon (LLM çıktısı doğrulanamadı: {'; '.join(problems)})"
        self.calls += 1
        return text.strip(), f"llm:{self.cfg.llm_backend} (doğrulandı)"

    def _prompt(self, case: dict) -> str:
        ev_lines = []
        for h in case["tespitler"]:
            ev_lines.append(
                f"- TESPİT {h['kural']} {h['ad']}: {h['aciklama']}; kanıt olay kimlikleri: {', '.join(h['kanit']) or 'seri'}"
            )
        for k, v in case["kanit_serileri"].items():
            ev_lines.append(f"- SERİ {k}: {', '.join(v)}")
        return (
            f"VAKA {case['case_id']} — kullanıcı {case['kullanici']} (departman {case['departman']}), gün {case['gun']}, risk {case['risk']}/100.\n"
            f"KANIT:\n" + "\n".join(ev_lines) + "\nBu kanıtlara dayanarak analist için özet yaz."
        )

    def _ollama(self, prompt: str) -> str:
        body = json.dumps(dict(model=self.cfg.ollama_model, system=self.SYSTEM, prompt=prompt, stream=False)).encode()
        req = urllib.request.Request(
            f"{self.cfg.ollama_url}/api/generate", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())["response"]

    def _anthropic(self, prompt: str) -> str:
        import anthropic  # opsiyonel bağımlılık: pip install anthropic ; kimlik: ANTHROPIC_API_KEY veya `ant auth login`

        client = anthropic.Anthropic()
        try:
            resp = client.messages.create(
                model=self.cfg.anthropic_model,
                max_tokens=1024,
                system=self.SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError:
            raise RuntimeError("Anthropic oran sınırı")
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Anthropic API hatası {e.status_code}")
        except anthropic.APIConnectionError:
            raise RuntimeError("Anthropic bağlantı hatası")
        if resp.stop_reason == "refusal":
            raise RuntimeError("model yanıtı reddetti")
        self.tokens += resp.usage.input_tokens + resp.usage.output_tokens
        return "".join(b.text for b in resp.content if b.type == "text")

    @staticmethod
    def _validate(text: str, case: dict) -> Tuple[bool, List[str]]:
        """15.3 Çıktı doğrulaması: geçen olay kimlikleri ve takma adlar girdi ile programatik olarak karşılaştırılır."""
        import re

        allowed_ev = {e for h in case["tespitler"] for e in h["kanit"]} | {e for v in case["kanit_serileri"].values() for e in v}
        problems = []
        refs = set(re.findall(r"E-[0-9a-f]{6,8}", text))
        bad = refs - allowed_ev
        if bad:
            problems.append(f"kanıtta olmayan olay kimlikleri: {sorted(bad)[:3]}")
        if not refs and not re.search(r"\[(seri|graf|ik)", text):
            problems.append("hiçbir olay referansı yok")
        users = set(re.findall(r"U-\d{4}", text))
        allowed_users = (
            {case["kullanici"]}
            | {s["diger_kullanici"] for s in case["graf"]["paylasilan_cihazlar"]}
            | {u for c in case["graf"]["ortak_noktalar"] for u in c["riskli_kullanicilar"]}
        )
        if users - allowed_users:
            problems.append(f"vakada olmayan kullanıcı adı: {sorted(users - allowed_users)[:3]}")
        return not problems, problems
