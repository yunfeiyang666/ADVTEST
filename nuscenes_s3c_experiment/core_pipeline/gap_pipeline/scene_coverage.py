"""
Gap Pipeline — ID-based Coverage Map

Coverage is tracked at the edge-instance level using unique object IDs:

  "edge" cell : keyed by (src_id, tgt_id)
               — one cell per directed edge in the scene graph.
               — initialised from scene-analysis Cypher results.

  "L2A"  cell : keyed by (anc_id, src_id, tgt_id)
               — ancestor → src → tgt two-hop chain.
               — created dynamically when update() is called.

  "L2B"  cell : keyed by (src_id, tgt_id, beyond_id)
               — src → tgt → beyond two-hop chain.
               — created dynamically when update() is called.

Usage
-----
    from gap_pipeline.scene_coverage import CoverageMap, SceneCoverageCalculator

    calc = SceneCoverageCalculator(neo4j_driver)
    cmap = calc.build_coverage_map(llm_client)         # initialise all edge cells

    # ... generate QA pairs and call:
    for qa in qa_list:
        cmap.update(qa)                                # mark edge (+ L2 chains) covered

    gaps = cmap.get_gap_cells(level="edge")            # returns uncovered edge dicts
    print(cmap.stats())
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# CoverageMap
# =============================================================================

class CoverageMap:
    """ID-based coverage counter for scene-graph edges.

    After ``init_from_records()`` the map contains one **edge** cell per
    directed edge found in the scene.  L2A/L2B cells are registered
    dynamically whenever ``update()`` is called with a QA pair whose
    ``cell_info`` includes ``anc_id`` or ``beyond_id``.
    """

    def __init__(self) -> None:
        # edge-level: {(src_id, tgt_id): count}
        self._edge_counts: Dict[tuple, int] = {}
        # edge metadata: {(src_id, tgt_id): {...9 fields...}}
        self._edge_info:   Dict[tuple, Dict[str, str]] = {}
        # L2A: {(anc_id, src_id, tgt_id): count}
        self._l2a_counts:  Dict[tuple, int] = {}
        # L2B: {(src_id, tgt_id, beyond_id): count}
        self._l2b_counts:  Dict[tuple, int] = {}

    # ── key constructors ─────────────────────────────────────────────────────

    @staticmethod
    def _edge_key(src_id: str, tgt_id: str) -> tuple:
        return (src_id, tgt_id)

    @staticmethod
    def _l2a_key(anc_id: str, src_id: str, tgt_id: str) -> tuple:
        return (anc_id, src_id, tgt_id)

    @staticmethod
    def _l2b_key(src_id: str, tgt_id: str, beyond_id: str) -> tuple:
        return (src_id, tgt_id, beyond_id)

    # ── initialisation ───────────────────────────────────────────────────────

    def init_from_records(self, records: List[Dict[str, Any]]) -> None:
        """Populate edge cells from scene-analysis Cypher result rows.

        Each record must contain ``src_id`` and ``tgt_id``; the remaining
        fields (types, statuses, directions, distance) are stored as metadata
        for later question generation.

        Parameters
        ----------
        records : list of dict
            One dict per edge, with keys:
            ``src_id``, ``src_type``, ``src_status``,
            ``tgt_id``, ``tgt_type``, ``tgt_status``,
            ``dir4``, ``dir8``, ``dist_level``.
        """
        for rec in records:
            src_id = rec.get("src_id") or ""
            tgt_id = rec.get("tgt_id") or ""
            if not src_id or not tgt_id:
                continue
            key = self._edge_key(src_id, tgt_id)
            self._edge_info[key] = {
                "src_id":     src_id,
                "src_type":   rec.get("src_type", "") or "",
                "src_status": rec.get("src_status", "") or "",
                "tgt_id":     tgt_id,
                "tgt_type":   rec.get("tgt_type", "") or "",
                "tgt_status": rec.get("tgt_status", "") or "",
                "dir4":       rec.get("dir4", "") or "",
                "dir8":       rec.get("dir8", "") or "",
                "dist_level": rec.get("dist_level", "") or "",
            }
            self._edge_counts.setdefault(key, 0)

        logger.info(
            "CoverageMap initialised: %d edge cells", len(self._edge_counts)
        )

    # ── incremental update ───────────────────────────────────────────────────

    def update(self, qa_pair: Dict[str, Any]) -> None:
        """Increment coverage counters from a generated QA pair.

        Reads ``qa_pair["cell_info"]`` which must contain at minimum:
        ``src_id``, ``tgt_id``.  Optionally ``anc_id`` and/or ``beyond_id``
        trigger L2A / L2B counter increments.

        Parameters
        ----------
        qa_pair : dict
            A QA pair dict as returned by ``GapQAGenerator._make_qa()``.
        """
        ci = qa_pair.get("cell_info", {})
        if not ci:
            return

        src_id    = ci.get("src_id", "") or ""
        tgt_id    = ci.get("tgt_id", "") or ""
        anc_id    = ci.get("anc_id", "") or ""
        beyond_id = ci.get("beyond_id", "") or ""

        if src_id and tgt_id:
            k = self._edge_key(src_id, tgt_id)
            self._edge_counts[k] = self._edge_counts.get(k, 0) + 1

        if anc_id and src_id and tgt_id:
            k = self._l2a_key(anc_id, src_id, tgt_id)
            self._l2a_counts[k] = self._l2a_counts.get(k, 0) + 1

        if src_id and tgt_id and beyond_id:
            k = self._l2b_key(src_id, tgt_id, beyond_id)
            self._l2b_counts[k] = self._l2b_counts.get(k, 0) + 1

    # ── gap queries ──────────────────────────────────────────────────────────

    def get_gap_cells(
        self,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return uncovered cells as a list of dicts.

        Parameters
        ----------
        level : None | "edge" | "L2A" | "L2B"
            Filter by level.  ``None`` returns cells from all levels.

        Returns
        -------
        list of dict
            Each dict has a ``"level"`` key plus the relevant ID / metadata
            fields.  "edge" cells include all nine metadata fields.
        """
        result: List[Dict[str, Any]] = []

        if level in (None, "edge"):
            for key, cnt in self._edge_counts.items():
                if cnt == 0:
                    cell = dict(self._edge_info.get(key, {}))
                    cell["level"] = "edge"
                    result.append(cell)

        if level in (None, "L2A"):
            for key, cnt in self._l2a_counts.items():
                if cnt == 0:
                    anc_id, src_id, tgt_id = key
                    result.append(
                        {
                            "level":  "L2A",
                            "anc_id": anc_id,
                            "src_id": src_id,
                            "tgt_id": tgt_id,
                        }
                    )

        if level in (None, "L2B"):
            for key, cnt in self._l2b_counts.items():
                if cnt == 0:
                    src_id, tgt_id, beyond_id = key
                    result.append(
                        {
                            "level":     "L2B",
                            "src_id":    src_id,
                            "tgt_id":    tgt_id,
                            "beyond_id": beyond_id,
                        }
                    )

        return result

    # ── statistics ───────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return per-level coverage statistics.

        Returns
        -------
        dict
            Keys: ``"edge"``, ``"L2A"``, ``"L2B"``.
            Each value has ``total``, ``covered``, ``gap``, ``rate`` (%).
        """
        def _agg(counts: Dict[tuple, int]) -> Dict[str, Any]:
            total   = len(counts)
            covered = sum(1 for c in counts.values() if c > 0)
            return {
                "total":   total,
                "covered": covered,
                "gap":     total - covered,
                "rate":    round(covered / total * 100, 2) if total else 0.0,
            }

        return {
            "edge": _agg(self._edge_counts),
            "L2A":  _agg(self._l2a_counts),
            "L2B":  _agg(self._l2b_counts),
        }


# =============================================================================
# SceneCoverageCalculator
# =============================================================================

class SceneCoverageCalculator:
    """Build and manage a :class:`CoverageMap` for a single scene via Neo4j.

    Parameters
    ----------
    neo4j_driver : neo4j.Driver
        An already-initialised Neo4j driver instance.  Must not be ``None``.
    """

    def __init__(self, neo4j_driver) -> None:
        if neo4j_driver is None:
            raise ValueError(
                "neo4j_driver must not be None — "
                "coverage calculation requires a live Neo4j connection."
            )
        self._driver = neo4j_driver

    def close(self) -> None:
        """Close the underlying Neo4j driver."""
        self._driver.close()

    # ── CoverageMap construction ──────────────────────────────────────────────

    def build_coverage_map(self, llm_client) -> CoverageMap:
        """Ask the LLM to write a scene-analysis Cypher, execute it, and
        return an initialised :class:`CoverageMap`.

        The Cypher must return one row per edge with columns:
        ``src_id``, ``src_type``, ``src_status``,
        ``tgt_id``, ``tgt_type``, ``tgt_status``,
        ``dir4``, ``dir8``, ``dist_level``.

        Parameters
        ----------
        llm_client : LLMClient
            Must implement ``generate_scene_analysis_cypher() -> str``.

        Returns
        -------
        CoverageMap
            Populated with one edge cell per directed edge in the scene.
        """
        cypher = llm_client.generate_scene_analysis_cypher()
        logger.debug("Scene-analysis Cypher:\n%s", cypher)

        with self._driver.session() as session:
            records = [dict(rec) for rec in session.run(cypher)]

        cmap = CoverageMap()
        cmap.init_from_records(records)
        logger.info(
            "build_coverage_map: %d edge cells initialised", len(cmap._edge_counts)
        )
        return cmap

    # ── gap query convenience method ──────────────────────────────────────────

    def get_gap_cells(
        self,
        coverage_map: CoverageMap,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return uncovered cells from *coverage_map*.

        Parameters
        ----------
        coverage_map : CoverageMap
        level : None | "edge" | "L2A" | "L2B"
        """
        return coverage_map.get_gap_cells(level=level)
