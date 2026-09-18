"""Graf erişim soyutlaması (add_edge, neighbors, paths_between, subgraph) ve NetworkX uygulaması — 14.3."""

from __future__ import annotations

from typing import Iterable, List, Optional, Set, Tuple

import networkx as nx
import pandas as pd


class GraphStore:
    def add_edge(self, src: str, dst: str, etype: str, ts: pd.Timestamp, **attrs) -> None:
        raise NotImplementedError

    def neighbors(
        self, node: str, etype: Optional[str] = None, since: Optional[pd.Timestamp] = None, direction: str = "any"
    ) -> List[Tuple[str, str, dict]]:
        raise NotImplementedError

    def paths_between(self, src: str, dst: str, max_hops: int = 3, since: Optional[pd.Timestamp] = None) -> List[List[str]]:
        raise NotImplementedError

    def subgraph(self, nodes: Iterable[str]):
        raise NotImplementedError


class NetworkXGraphStore(GraphStore):
    """Kenarlar (src,dst) bazında toplanır; her kenar etype → {count, first_ts, last_ts} taşır (zaman damgası zorunlu, 11.3)."""

    def __init__(self):
        self.g = nx.DiGraph()

    @staticmethod
    def ntype(node: str) -> str:
        return node.split(":", 1)[0]

    def add_edge(self, src: str, dst: str, etype: str, ts: pd.Timestamp, **attrs) -> None:
        for n in (src, dst):
            if n not in self.g:
                self.g.add_node(n, ntype=self.ntype(n))
        if not self.g.has_edge(src, dst):
            self.g.add_edge(src, dst, rel={})
        rel = self.g[src][dst]["rel"]
        n = attrs.pop("count", 1)
        r = rel.setdefault(etype, dict(count=0, first_ts=ts, last_ts=ts, **attrs))
        r["count"] += n
        r["first_ts"], r["last_ts"] = min(r["first_ts"], ts), max(r["last_ts"], ts)

    def neighbors(self, node, etype=None, since=None, direction="any"):
        out = []
        if node not in self.g:
            return out
        iters = []
        if direction in ("out", "any"):
            iters.append((node, v, self.g[node][v]["rel"]) for v in self.g.successors(node))
        if direction in ("in", "any"):
            iters.append((u, node, self.g[u][node]["rel"]) for u in self.g.predecessors(node))
        for it in iters:
            for a, b, rel in it:
                for et, meta in rel.items():
                    if etype and et != etype:
                        continue
                    if since is not None and meta["last_ts"] < since:
                        continue
                    out.append((a if a != node else b, et, meta))
        return out

    def _window_view(self, since, node_types: Optional[Set[str]] = None, allow_nodes: Iterable[str] = ()):
        """Zaman penceresi + düğüm tipi filtresi: 'intranet' gibi herkesin bağlandığı hub düğümler (app/geo/ip) yol sayılmaz."""
        allow = set(allow_nodes)

        def keep_edge(u, v):
            return since is None or any(m["last_ts"] >= since for m in self.g[u][v]["rel"].values())

        def keep_node(n):
            return node_types is None or n in allow or self.g.nodes[n].get("ntype") in node_types

        return nx.subgraph_view(self.g, filter_node=keep_node, filter_edge=keep_edge).to_undirected(as_view=True)

    def paths_between(self, src, dst, max_hops=3, since=None, node_types: Optional[Set[str]] = None):
        if src not in self.g or dst not in self.g:
            return []
        view = self._window_view(since, node_types, allow_nodes=(src, dst))
        try:
            return [p for _, p in zip(range(25), nx.all_simple_paths(view, src, dst, cutoff=max_hops))]
        except nx.NetworkXNoPath:
            return []

    def subgraph(self, nodes):
        return self.g.subgraph(list(nodes))

    # ---- kalıcılık ve budama (11.3 graf sürekli güncellenir; 20.1 saklama süresi) ----
    def export_edges(self) -> List[dict]:
        rows = []
        for u, v, data in self.g.edges(data=True):
            for et, m in data["rel"].items():
                rows.append(
                    dict(
                        src=u,
                        dst=v,
                        etype=et,
                        count=int(m["count"]),
                        first_ts=m["first_ts"].isoformat(),
                        last_ts=m["last_ts"].isoformat(),
                    )
                )
        return rows

    def import_edges(self, rows: Iterable[dict]) -> int:
        n = 0
        for r in rows:
            first, last = pd.Timestamp(r["first_ts"]), pd.Timestamp(r["last_ts"])
            self.add_edge(r["src"], r["dst"], r["etype"], first, count=int(r["count"]))
            self.g[r["src"]][r["dst"]]["rel"][r["etype"]]["last_ts"] = max(last, first)
            n += 1
        return n

    def prune(self, before: pd.Timestamp) -> int:
        """Son görülme tarihi eşikten eski kenarları ve yalnız kalan düğümleri kaldırır."""
        removed = 0
        for u, v in list(self.g.edges()):
            rel = self.g[u][v]["rel"]
            for et in [et for et, m in rel.items() if m["last_ts"] < before]:
                del rel[et]
                removed += 1
            if not rel:
                self.g.remove_edge(u, v)
        self.g.remove_nodes_from([n for n in list(self.g.nodes) if self.g.degree(n) == 0 and not self.g.nodes[n].get("critical")])
        return removed

    def reachable_within(self, node: str, hops: int, since=None, node_types: Optional[Set[str]] = None) -> Set[str]:
        if node not in self.g:
            return set()
        view = self._window_view(since, node_types)
        return set(nx.single_source_shortest_path_length(view, node, cutoff=hops)) - {node}
