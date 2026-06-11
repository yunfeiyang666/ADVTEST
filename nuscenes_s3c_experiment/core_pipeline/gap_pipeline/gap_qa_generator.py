"""
Gap Pipeline — GapQAGenerator

Generates QA pairs for scene-graph edges that have not yet been covered by
any existing question.

Flow (per "edge"-level gap cell)
---------------------------------
1. ``LLMClient.generate_gap_context_cypher(cell)``
       → Cypher query string that pinpoints the edge (by src_id / tgt_id) and
         optionally retrieves one-hop L2 context nodes (anc, beyond).

2. Neo4j executes the Cypher  → one result row with up to 13 fields:
       src_id, src_type, src_status,
       tgt_id, tgt_type, tgt_status,
       dir4, dir8, dist_level,
       anc_id, anc_type,
       beyond_id, beyond_type

3. ``get_applicable_templates(tvars)``
       → list of template IDs whose ``requires`` conditions are met.

4. For each template: pick a random variant, fill variables, resolve answer.

5. Each QA pair carries ``cell_info = {src_id, tgt_id, anc_id, beyond_id}``
   so that ``CoverageMap.update(qa_pair)`` can mark the cell covered.

Non-"edge" cells (L2A, L2B) are silently skipped; they are covered as a
side-effect of "edge" QA generation once anc_id / beyond_id are populated.
"""
from __future__ import annotations

import logging
import random
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GapQAGenerator:
    """Generate QA pairs for uncovered edge-level gap cells.

    Parameters
    ----------
    llm_client : LLMClient
        Instance of ``gap_pipeline.llm_client.LLMClient``.
        Used only to generate gap-context Cypher queries.
    neo4j_driver : neo4j.Driver
        Live Neo4j driver (``neo4j.GraphDatabase.driver(...)``).
    max_per_cell : int
        Maximum number of QA pairs to emit per gap cell (default 8).
    """

    def __init__(
        self,
        llm_client,
        neo4j_driver,
        max_per_cell: int = 8,
    ) -> None:
        self.llm = llm_client
        self._driver = neo4j_driver
        self.max_per_cell = max_per_cell

    # ── main entry point ─────────────────────────────────────────────────────

    def generate_from_gap_cells(
        self,
        gap_cells: List[Dict[str, Any]],
        scene_name: str = "",
        frame_idx: int = 0,
    ) -> List[Dict[str, Any]]:
        """Generate QA pairs for all "edge"-level gap cells.

        Cells with ``level != "edge"`` are skipped; they will be covered as a
        side-effect when their core edge is processed.

        Parameters
        ----------
        gap_cells : list of dict
            Output of ``CoverageMap.get_gap_cells()``.
        scene_name : str
            Written into each QA pair's metadata.
        frame_idx : int
            Written into each QA pair's metadata.

        Returns
        -------
        list of dict
            QA pair dicts (compatible with ``CoverageMap.update()``).
        """
        results: List[Dict[str, Any]] = []
        for cell in gap_cells:
            if cell.get("level", "") != "edge":
                continue
            src_id = cell.get("src_id", "?")
            tgt_id = cell.get("tgt_id", "?")
            try:
                qa_list = self._process_cell(cell, scene_name, frame_idx)
                results.extend(qa_list)
                logger.info(
                    "gap cell %s→%s: generated %d QA pairs",
                    src_id, tgt_id, len(qa_list),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Skipping gap cell %s→%s: %s", src_id, tgt_id, exc
                )
        return results

    # ── per-cell processing ──────────────────────────────────────────────────

    def _process_cell(
        self,
        gap_cell: Dict[str, Any],
        scene_name: str,
        frame_idx: int,
    ) -> List[Dict[str, Any]]:
        """LLM → Cypher → Neo4j → template fill for one gap cell.

        Parameters
        ----------
        gap_cell : dict
            Must have at least ``src_id``, ``tgt_id``, and ``dir8``.
            Other fields (types, statuses, etc.) are used as fallbacks if the
            Cypher result row is incomplete.
        """
        # Step 1: LLM generates context-lookup Cypher
        cypher = self.llm.generate_gap_context_cypher(gap_cell)
        logger.debug("Gap-context Cypher:\n%s", cypher)

        # Step 2: execute in Neo4j
        with self._driver.session() as session:
            record = session.run(cypher).single()

        if record is None:
            logger.warning(
                "Gap-context query returned no rows for %s→%s",
                gap_cell.get("src_id"), gap_cell.get("tgt_id"),
            )
            return []

        ctx: Dict[str, Any] = dict(record)

        # Step 3: fill templates
        return self._fill_templates(ctx, gap_cell, scene_name, frame_idx)

    # ── template filling ─────────────────────────────────────────────────────

    def _fill_templates(
        self,
        ctx: Dict[str, Any],
        gap_cell: Dict[str, Any],
        scene_name: str,
        frame_idx: int,
    ) -> List[Dict[str, Any]]:
        """Select applicable templates, fill variables, resolve answers.

        Template variables are derived from ``ctx`` (Neo4j result), with
        ``gap_cell`` fields used as fallbacks when the Cypher result is
        missing a value.

        Parameters
        ----------
        ctx : dict
            One-row result from the gap-context Cypher.
        gap_cell : dict
            Original gap cell dict (used for fallback values).
        """
        from .gap_templates import (
            TEMPLATE_META,
            get_applicable_templates,
            pick_variation,
            resolve_answer,
        )

        # ── build template variable dict (all strings) ─────────────────────
        def _s(v: Any) -> str:
            """Coerce a possibly-None value to a non-None string."""
            return str(v) if v is not None else ""

        tvars: Dict[str, str] = {
            "src_id":     _s(ctx.get("src_id")     or gap_cell.get("src_id")),
            "src_type":   _s(ctx.get("src_type")   or gap_cell.get("src_type")),
            "src_status": _s(ctx.get("src_status") or gap_cell.get("src_status")),
            "tgt_id":     _s(ctx.get("tgt_id")     or gap_cell.get("tgt_id")),
            "tgt_type":   _s(ctx.get("tgt_type")   or gap_cell.get("tgt_type")),
            "tgt_status": _s(ctx.get("tgt_status") or gap_cell.get("tgt_status")),
            "dir4":       _s(ctx.get("dir4")        or gap_cell.get("dir4")),
            "dir8":       _s(ctx.get("dir8")        or gap_cell.get("dir8")),
            "dist_level": _s(ctx.get("dist_level") or gap_cell.get("dist_level")),
            # L2A context (may be empty if Neo4j found no ancestor)
            "anc_id":     _s(ctx.get("anc_id")   or ""),
            "anc_type":   _s(ctx.get("anc_type") or ""),
            # L2B context (may be empty if Neo4j found no beyond node)
            "beyond_id":   _s(ctx.get("beyond_id")   or ""),
            "beyond_type": _s(ctx.get("beyond_type") or ""),
        }

        # ── cell_info carries IDs for CoverageMap.update() ─────────────────
        cell_info: Dict[str, str] = {
            "src_id":    tvars["src_id"],
            "tgt_id":    tvars["tgt_id"],
            "anc_id":    tvars["anc_id"],
            "beyond_id": tvars["beyond_id"],
        }

        # ── select + shuffle applicable templates ──────────────────────────
        applicable = get_applicable_templates(tvars)
        random.shuffle(applicable)

        qa_list: List[Dict[str, Any]] = []
        for tmpl_id in applicable:
            meta = TEMPLATE_META[tmpl_id]

            # fill template string
            try:
                question = pick_variation(tmpl_id).format(**tvars)
            except KeyError:
                continue

            # resolve answer
            answer = resolve_answer(tmpl_id, tvars)
            if not answer:
                continue

            qa_list.append(
                self._make_qa(
                    scene_name=scene_name,
                    frame_idx=frame_idx,
                    template_id=tmpl_id,
                    difficulty=meta["difficulty"],
                    question_type=meta["category"],
                    question=question,
                    answer=answer,
                    answer_type=meta["answer_type"],
                    src_id=tvars["src_id"],
                    tgt_id=tvars["tgt_id"],
                    cell_info=cell_info,
                )
            )

            if len(qa_list) >= self.max_per_cell:
                break

        return qa_list

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_qa(
        scene_name: str,
        frame_idx: int,
        template_id: str,
        difficulty: str,
        question_type: str,
        question: str,
        answer: str,
        answer_type: str,
        src_id: str,
        tgt_id: str,
        cell_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Construct a QA pair dict compatible with the pipeline schema.

        The ``cell_info`` field is consumed by ``CoverageMap.update()`` to
        mark the corresponding edge (and optional L2 chains) as covered.
        """
        return {
            "question_id":       str(uuid.uuid4())[:8],
            "scene_name":        scene_name,
            "frame_idx":         frame_idx,
            "template_id":       template_id,
            "difficulty":        difficulty,
            "question_type":     question_type,
            "question":          question,
            "answer":            answer,
            "answer_type":       answer_type,
            "reference_objects": [src_id],
            "target_objects":    [tgt_id],
            "source":            "gap_fill",
            "cell_info":         cell_info or {},
        }


# =============================================================================
# Convenience function
# =============================================================================

def fill_gap_cells(
    gap_cells: List[Dict[str, Any]],
    neo4j_uri: str = "bolt://localhost:7600",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "12345678",
    scene_name: str = "",
    frame_idx: int = 0,
    max_per_cell: int = 8,
) -> List[Dict[str, Any]]:
    """One-call convenience wrapper for gap-cell QA generation.

    Parameters
    ----------
    gap_cells : list of dict
        Output of ``CoverageMap.get_gap_cells(level="edge")``.
    neo4j_uri / neo4j_user / neo4j_password :
        Neo4j connection parameters.
    scene_name, frame_idx :
        Written into QA metadata.
    max_per_cell : int
        Maximum QA pairs per gap cell.

    Returns
    -------
    list of dict
        QA pair dicts ready for serialisation.
    """
    from neo4j import GraphDatabase  # type: ignore[import]

    from .llm_client import LLMClient

    llm    = LLMClient()
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    gen    = GapQAGenerator(llm, driver, max_per_cell=max_per_cell)
    try:
        return gen.generate_from_gap_cells(
            gap_cells, scene_name=scene_name, frame_idx=frame_idx
        )
    finally:
        driver.close()
