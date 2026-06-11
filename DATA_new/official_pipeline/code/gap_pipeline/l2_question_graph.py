"""
Explicit question graph for L2 coverage footprint.

This module is a side-path implementation for the L2 refactor. It does not
modify the existing pipeline. Coverage is extracted only from spatial relations
explicitly expressed by a generated question.

Rules:
  L0 = explicit nodes
  L1 = explicit edges
  L2 = all length-2 simple paths in the explicit question graph

No global scene-graph edge completion and no arbitrary pairwise combination of
mentioned objects are allowed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Set, Tuple


def canon_l1(u: str, v: str) -> str:
    """Canonical undirected L1 key."""
    a, b = sorted([str(u), str(v)])
    return f"{a}|{b}"


def canon_l2(u: str, pivot: str, v: str) -> str:
    """Canonical L2 key: endpoints sorted, pivot fixed."""
    a, c = sorted([str(u), str(v)])
    return f"{a}|{pivot}|{c}"


@dataclass(frozen=True)
class QEdge:
    """A spatial relation explicitly expressed in a question."""

    u: str
    v: str
    relation: str = ""
    source: str = "template"  # template | constraint | answer_slot

    def key(self) -> str:
        return canon_l1(self.u, self.v)


@dataclass
class CoverageFootprint:
    """Extracted coverage keys from an explicit question graph."""

    l0: Set[str] = field(default_factory=set)
    l1: Set[str] = field(default_factory=set)
    l2: Set[str] = field(default_factory=set)

    def as_dict(self) -> Dict[str, List[str]]:
        return {
            "l0": sorted(self.l0),
            "l1": sorted(self.l1),
            "l2": sorted(self.l2),
        }


@dataclass
class QuestionGraph:
    """Explicit subgraph encoded by a generated question."""

    template_family: str
    nodes: Set[str] = field(default_factory=set)
    edges: List[QEdge] = field(default_factory=list)
    answer_nodes: Set[str] = field(default_factory=set)
    meta: Dict = field(default_factory=dict)

    def add_node(self, node_id: str, *, answer: bool = False) -> None:
        if not node_id:
            return
        nid = str(node_id)
        self.nodes.add(nid)
        if answer:
            self.answer_nodes.add(nid)

    def add_edge(
        self,
        u: str,
        v: str,
        *,
        relation: str = "",
        source: str = "template",
    ) -> None:
        if not u or not v or str(u) == str(v):
            return
        self.add_node(str(u))
        self.add_node(str(v))
        edge = QEdge(str(u), str(v), relation=relation, source=source)
        if edge.key() not in {e.key() for e in self.edges}:
            self.edges.append(edge)

    def adjacency(self) -> Dict[str, Set[str]]:
        adj: Dict[str, Set[str]] = {n: set() for n in self.nodes}
        for e in self.edges:
            adj.setdefault(e.u, set()).add(e.v)
            adj.setdefault(e.v, set()).add(e.u)
        return adj

    def footprint(self) -> CoverageFootprint:
        fp = CoverageFootprint()
        fp.l0.update(self.nodes)
        fp.l1.update(e.key() for e in self.edges)

        adj = self.adjacency()
        for pivot, neighs in adj.items():
            for u, v in combinations(sorted(neighs), 2):
                if u != v and u != pivot and v != pivot:
                    fp.l2.add(canon_l2(u, pivot, v))
        return fp


# Convenience constructors used by future template families.

def converge_graph(
    a_id: str,
    x_id: str,
    c_id: str,
    *,
    refs: Optional[Iterable[str]] = None,
    family: str = "converge",
) -> QuestionGraph:
    """Build explicit graph for a -> x <- c, optionally with refs -> x."""
    g = QuestionGraph(template_family=family)
    g.add_node(x_id, answer=True)
    g.add_edge(a_id, x_id, source="template")
    g.add_edge(c_id, x_id, source="template")
    for ref in refs or []:
        g.add_edge(ref, x_id, source="constraint")
    return g


def diverge_graph(
    x_id: str,
    b_id: str,
    y_id: str,
    *,
    x_refs: Optional[Iterable[str]] = None,
    y_refs: Optional[Iterable[str]] = None,
    family: str = "diverge_compare",
) -> QuestionGraph:
    """Build explicit graph for x <- b -> y plus branch-local refs."""
    g = QuestionGraph(template_family=family)
    g.add_edge(x_id, b_id, source="template")
    g.add_edge(b_id, y_id, source="template")
    for ref in x_refs or []:
        g.add_edge(ref, x_id, source="constraint")
    for ref in y_refs or []:
        g.add_edge(ref, y_id, source="constraint")
    return g


def chain_graph(a_id: str, b_id: str, c_id: str, *, family: str) -> QuestionGraph:
    """Build explicit graph for chain-style templates over original a-b-c."""
    g = QuestionGraph(template_family=family)
    g.add_edge(a_id, b_id, source="template")
    g.add_edge(b_id, c_id, source="template")
    return g

