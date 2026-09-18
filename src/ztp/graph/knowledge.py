"""Bilgi grafı: MITRE ATT&CK alt kümesi (tüm müşterilerde ortak, yavaş değişir) — 11.3."""

from __future__ import annotations

from typing import List

import pandas as pd

from ztp.graph.store import NetworkXGraphStore

ATTACK_TECHNIQUES = {
    "T1078": ("Valid Accounts", "Initial Access"),
    "T1078.003": ("Valid Accounts: Local Accounts", "Persistence"),
    "T1204": ("User Execution", "Execution"),
    "T1567": ("Exfiltration Over Web Service", "Exfiltration"),
    "T1110": ("Brute Force", "Credential Access"),
    "T1039": ("Data from Network Shared Drive", "Collection"),
    "T1530": ("Data from Cloud Storage", "Collection"),
    "T1087": ("Account Discovery", "Discovery"),
    "T1018": ("Remote System Discovery", "Discovery"),
    "T1562": ("Impair Defenses", "Defense Evasion"),
    "T1052": ("Exfiltration Over Physical Medium", "Exfiltration"),
    "T1021": ("Remote Services", "Lateral Movement"),
}
# Örnek grup→teknik ilişkileri (gerçek besleme: ATT&CK STIX / tehdit istihbaratı; burada yalnızca yapıyı gösterir)
THREAT_GROUPS_SAMPLE = {"APT29": ["T1078", "T1021", "T1087"], "FIN7": ["T1204", "T1567"], "Lapsus$": ["T1078", "T1110", "T1530"]}


class KnowledgeGraph:
    def __init__(self):
        self.store = NetworkXGraphStore()
        t0 = pd.Timestamp("2000-01-01")
        for tid, (name, tactic) in ATTACK_TECHNIQUES.items():
            self.store.add_edge(f"technique:{tid}", f"tactic:{tactic}", "ait_oldugu", t0, name=name)
        for grp, techs in THREAT_GROUPS_SAMPLE.items():
            for tid in techs:
                self.store.add_edge(f"group:{grp}", f"technique:{tid}", "kullanir", t0)

    def tactic(self, tid: str) -> str:
        return ATTACK_TECHNIQUES.get(tid, ("?", "Bilinmiyor"))[1]

    def technique_name(self, tid: str) -> str:
        return ATTACK_TECHNIQUES.get(tid, ("Bilinmeyen teknik", "?"))[0]

    def groups_using(self, tid: str) -> List[str]:
        return sorted(n.split(":", 1)[1] for n, et, _ in self.store.neighbors(f"technique:{tid}", "kullanir", direction="in"))
