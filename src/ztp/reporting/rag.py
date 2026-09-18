"""ATT&CK bilgi tabanı — RAG bağlamı (ADR-009: RAG yalnızca analist açıklaması ve raporlama için; skorlamada yer almaz).

Injection'a kapalı tasarım:
- Getirme (retrieval) yalnızca TESPİT TANIMINDAKİ teknik kimlikleriyle, tam eşleşmeyle yapılır. Log kaynaklı serbest
  metin (cihaz adı, URL, komut satırı) asla sorgu olarak kullanılmaz; saldırgan hangi pasajın getirileceğini seçemez.
- Bilgi tabanı paketle gelir, sürümlüdür ve SHA-256 manifesti ile doğrulanır; değiştirilmiş dosya reddedilir
  (bilgi tabanı zehirlenmesi / dolaylı prompt injection). Harici besleme eklenecekse aynı temizleme ve manifest süreci uygulanır.
- Getirilen pasajlar da "veri" olarak temizlenir ve nonce'lu blokta modele verilir; pasajlar talimat içeremez.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

import yaml

from ztp.reporting.sanitize import sanitize_identifier, sanitize_text

LOG = logging.getLogger(__name__)
KB_DIR = Path(__file__).resolve().parent / "knowledge"
KB_FILE = "attack.yaml"
MANIFEST_FILE = "MANIFEST.sha256"
TECHNIQUE_ID_MAX = 12


class KnowledgeBaseIntegrityError(RuntimeError):
    """Bilgi tabanı dosyası manifestle uyuşmuyor (değiştirilmiş/zehirlenmiş olabilir)."""


@dataclass(frozen=True)
class Passage:
    technique: str
    name: str
    tactic: str
    summary: str
    detection: str
    mitigations: str
    source: str
    kb_version: str

    def as_text(self) -> str:
        return f"{self.technique} ({self.name}, {self.tactic}): {self.summary} Tespit: {self.detection} Önlem: {self.mitigations}"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def write_manifest(kb_dir: Union[str, Path] = KB_DIR) -> Path:
    """Bilgi tabanı güncellendiğinde (gözden geçirilmiş, imzalı süreç) manifesti yeniden üretir."""
    kb_dir = Path(kb_dir)
    manifest = kb_dir / MANIFEST_FILE
    manifest.write_text(f"{file_sha256(kb_dir / KB_FILE)}  {KB_FILE}\n", encoding="utf-8")
    return manifest


class AttackKnowledgeBase:
    def __init__(self, kb_dir: Union[str, Path] = KB_DIR, verify: bool = True):
        self.kb_dir = Path(kb_dir)
        path = self.kb_dir / KB_FILE
        if verify:
            self._verify(path)
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        self.version = str(raw.get("version", "?"))
        self.source = sanitize_text(raw.get("source", ""), 120).text
        self._items: Dict[str, Passage] = {}
        for tid, item in (raw.get("techniques") or {}).items():
            key = sanitize_identifier(tid, TECHNIQUE_ID_MAX)
            fields = {k: sanitize_text(item.get(k, ""), 400) for k in ("name", "tactic", "summary", "detection", "mitigations")}
            if any(s.flags for s in fields.values()):
                # bilgi tabanında talimat benzeri içerik: pasaj yüklenmez, olay loglanır (dolaylı injection girişimi)
                LOG.error(
                    "Bilgi tabanı pasajı reddedildi (%s): talimat benzeri içerik %s", key, [s.flags for s in fields.values()]
                )
                continue
            self._items[key] = Passage(
                key,
                fields["name"].text,
                fields["tactic"].text,
                fields["summary"].text,
                fields["detection"].text,
                fields["mitigations"].text,
                self.source,
                self.version,
            )
        LOG.info(
            "ATT&CK bilgi tabanı: %d teknik, sürüm %s (bütünlük %s)",
            len(self._items),
            self.version,
            "doğrulandı" if verify else "doğrulanmadı",
        )

    def _verify(self, path: Path) -> None:
        manifest = self.kb_dir / MANIFEST_FILE
        if not manifest.exists():
            raise KnowledgeBaseIntegrityError(f"Manifest yok: {manifest}")
        expected = {}
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, name = line.split()
                expected[name.strip()] = digest.strip()
        actual = file_sha256(path)
        if expected.get(KB_FILE) != actual:
            raise KnowledgeBaseIntegrityError(
                f"{KB_FILE} manifestle uyuşmuyor (beklenen {expected.get(KB_FILE, '?')[:12]}…, hesaplanan {actual[:12]}…)"
            )

    def retrieve(self, technique_ids: Iterable[str], limit: int = 6) -> List[Passage]:
        """Yalnızca tam teknik kimliği ile getirme; bilinmeyen kimlikler sessizce atlanır (serbest metin arama YOK)."""
        out: List[Passage] = []
        seen = set()
        for tid in technique_ids:
            key = sanitize_identifier(tid, TECHNIQUE_ID_MAX)
            if key in self._items and key not in seen:
                out.append(self._items[key])
                seen.add(key)
            if len(out) >= limit:
                break
        return out

    def get(self, technique_id: str) -> Optional[Passage]:
        return self._items.get(sanitize_identifier(technique_id, TECHNIQUE_ID_MAX))

    def __len__(self) -> int:
        return len(self._items)
