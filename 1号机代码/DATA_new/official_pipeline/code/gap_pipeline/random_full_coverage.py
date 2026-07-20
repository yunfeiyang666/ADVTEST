"""Coverage-blind random sampling for the RQ2 full-coverage baseline.

The selector and the coverage tracker are deliberately separate.  The selector
only knows the immutable initial gap pool and the number of verified plans for
each gap.  Coverage is observed after a draw and can stop the run, but it can
never affect which gap or plan is drawn next.
"""
from __future__ import annotations

import hashlib
import gzip
import json
import os
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Sequence


MILESTONES = (0.50, 0.75, 0.90, 0.95, 0.99, 1.00)


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rng_state_to_json(state: tuple) -> list[Any]:
    return [state[0], list(state[1]), state[2]]


def _rng_state_from_json(state: Sequence[Any]) -> tuple:
    if len(state) != 3:
        raise ValueError("Invalid random state")
    return int(state[0]), tuple(int(value) for value in state[1]), state[2]


@dataclass(frozen=True)
class RandomDraw:
    gap_id: str
    plan_index: int
    plan_id: str


class VerifiedPlanCache:
    """Immutable, validated question records keyed by static random plan id.

    Random selection is intentionally unaware of this cache.  The cache only
    prevents a repeated draw of the same pre-verified plan from executing the
    deterministic programmatic realization again.  Each cached record retains
    the actual question text and coverage footprint produced by that pipeline.
    """

    SCHEMA = "rq2_verified_random_plan_cache_v1"

    def __init__(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        normalized: Dict[str, Dict[str, Any]] = {}
        for raw_plan_id, raw_record in records.items():
            plan_id = str(raw_plan_id)
            record = dict(raw_record)
            if not plan_id:
                raise ValueError("Verified random plan cache contains an empty plan id")
            if not str(record.get("question") or "").strip():
                raise ValueError(f"Verified random plan cache has no question: {plan_id}")
            footprint = record.get("coverage_footprint") or {}
            if not isinstance(footprint, Mapping):
                raise ValueError(f"Verified random plan cache has invalid footprint: {plan_id}")
            normalized[plan_id] = record
        self._records = normalized
        self._fingerprint = _stable_hash(
            {
                plan_id: {
                    "question": str(record.get("question") or ""),
                    "answer": record.get("answer"),
                    "template_id": str(record.get("template_id") or ""),
                    "coverage_footprint": record.get("coverage_footprint") or {},
                }
                for plan_id, record in sorted(self._records.items())
            }
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def plan_ids(self) -> set[str]:
        return set(self._records)

    def get(self, plan_id: str) -> Dict[str, Any]:
        try:
            return dict(self._records[plan_id])
        except KeyError as exc:
            raise KeyError(f"No cached record for random plan: {plan_id}") from exc

    def validate_plan_ids(self, expected_plan_ids: Iterable[str]) -> None:
        expected = {str(plan_id) for plan_id in expected_plan_ids}
        missing = expected - self.plan_ids
        extra = self.plan_ids - expected
        if missing or extra:
            raise ValueError(
                "Verified random plan cache does not match the static plan pool: "
                f"missing={len(missing)}, extra={len(extra)}"
            )

    def write(self, path: Path, *, candidate_fingerprint: str) -> None:
        payload = {
            "schema": self.SCHEMA,
            "candidate_fingerprint": str(candidate_fingerprint),
            "cache_fingerprint": self.fingerprint,
            "records": [
                {"plan_id": plan_id, "record": record}
                for plan_id, record in sorted(self._records.items())
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        encoded = json.dumps(payload, ensure_ascii=False)
        if path.suffix == ".gz":
            with gzip.open(temporary, "wt", encoding="utf-8") as handle:
                handle.write(encoded)
        else:
            temporary.write_text(encoded, encoding="utf-8")
        os.replace(temporary, path)

    @classmethod
    def load(cls, path: Path, *, candidate_fingerprint: str) -> "VerifiedPlanCache":
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != cls.SCHEMA:
            raise ValueError("Unsupported verified random plan cache schema")
        if payload.get("candidate_fingerprint") != str(candidate_fingerprint):
            raise ValueError("Verified random plan cache belongs to another candidate pool")
        records: Dict[str, Mapping[str, Any]] = {}
        for item in payload.get("records") or []:
            if not isinstance(item, Mapping):
                raise ValueError("Invalid verified random plan cache record")
            plan_id = str(item.get("plan_id") or "")
            record = item.get("record")
            if plan_id in records or not isinstance(record, Mapping):
                raise ValueError("Invalid or duplicate verified random plan cache entry")
            records[plan_id] = record
        cache = cls(records)
        if payload.get("cache_fingerprint") != cache.fingerprint:
            raise ValueError("Verified random plan cache fingerprint mismatch")
        return cache


class StaticRandomSelector:
    """Sample a fixed initial gap pool and its verified plans with replacement."""

    def __init__(
        self,
        gap_to_plan_ids: Mapping[str, Sequence[str]],
        *,
        seed: int,
    ) -> None:
        normalized: Dict[str, tuple[str, ...]] = {}
        for gap_id, plan_ids in gap_to_plan_ids.items():
            key = str(gap_id)
            plans = tuple(str(plan_id) for plan_id in plan_ids)
            if not plans:
                raise ValueError(f"Initial gap has no verified plan: {key}")
            if len(set(plans)) != len(plans):
                raise ValueError(f"Duplicate plan ids for initial gap: {key}")
            normalized[key] = plans
        if not normalized:
            raise ValueError("The initial random gap pool is empty")

        self._gap_to_plan_ids = normalized
        self._gap_ids = tuple(sorted(normalized))
        self._seed = int(seed)
        self._rng = random.Random(self._seed)
        self._draw_count = 0
        self._fingerprint = _stable_hash(
            {gap_id: list(normalized[gap_id]) for gap_id in self._gap_ids}
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def draw_count(self) -> int:
        return self._draw_count

    @property
    def seed(self) -> int:
        return self._seed

    def draw(self) -> RandomDraw:
        gap_id = self._gap_ids[self._rng.randrange(len(self._gap_ids))]
        plans = self._gap_to_plan_ids[gap_id]
        plan_index = self._rng.randrange(len(plans))
        self._draw_count += 1
        return RandomDraw(gap_id, plan_index, plans[plan_index])

    def state_dict(self) -> Dict[str, Any]:
        return {
            "schema": "rq2_static_random_selector_v1",
            "seed": self._seed,
            "draw_count": self._draw_count,
            "candidate_fingerprint": self._fingerprint,
            "rng_state": _rng_state_to_json(self._rng.getstate()),
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        if state.get("schema") != "rq2_static_random_selector_v1":
            raise ValueError("Unsupported selector checkpoint schema")
        if int(state.get("seed", -1)) != self._seed:
            raise ValueError("Selector checkpoint seed does not match")
        if state.get("candidate_fingerprint") != self._fingerprint:
            raise ValueError("Selector candidate pool changed since checkpoint")
        self._rng.setstate(_rng_state_from_json(state["rng_state"]))
        self._draw_count = int(state.get("draw_count", 0))


def _as_set(values: Iterable[Any]) -> set[str]:
    return {str(value) for value in values}


@dataclass
class CoverageAccumulator:
    """Observe selected questions without participating in selection."""

    universe_l0: set[str]
    universe_l1: set[str]
    universe_l2: set[str]
    covered_l0: set[str] = field(default_factory=set)
    covered_l1: set[str] = field(default_factory=set)
    covered_l2: set[str] = field(default_factory=set)
    draws: int = 0
    no_gain_draws: int = 0
    gap_counts: Counter[str] = field(default_factory=Counter)
    plan_counts: Counter[str] = field(default_factory=Counter)
    text_counts: Counter[str] = field(default_factory=Counter)
    milestones: Dict[str, Dict[str, int]] = field(default_factory=dict)
    coverage_rate_sums: Dict[str, float] = field(
        default_factory=lambda: {"l0": 0.0, "l1": 0.0, "l2": 0.0}
    )
    cumulative_gains: Dict[str, int] = field(
        default_factory=lambda: {"l0": 0, "l1": 0, "l2": 0}
    )

    @classmethod
    def create(
        cls,
        *,
        universe: Mapping[str, Iterable[Any]],
        initial_coverage: Mapping[str, Iterable[Any]],
    ) -> "CoverageAccumulator":
        instance = cls(
            universe_l0=_as_set(universe.get("l0", [])),
            universe_l1=_as_set(universe.get("l1", [])),
            universe_l2=_as_set(universe.get("l2", [])),
            covered_l0=_as_set(initial_coverage.get("l0", [])),
            covered_l1=_as_set(initial_coverage.get("l1", [])),
            covered_l2=_as_set(initial_coverage.get("l2", [])),
        )
        if not instance.universe_l2:
            raise ValueError("L2 universe is empty")
        instance._validate_coverage()
        instance._record_milestones()
        return instance

    def _validate_coverage(self) -> None:
        for level in ("l0", "l1", "l2"):
            covered = getattr(self, f"covered_{level}")
            universe = getattr(self, f"universe_{level}")
            extra = covered - universe
            if extra:
                raise ValueError(
                    f"Initial {level.upper()} coverage contains values outside the universe: "
                    f"{sorted(extra)[:3]}"
                )

    def rate(self, level: str) -> float:
        universe = getattr(self, f"universe_{level}")
        covered = getattr(self, f"covered_{level}")
        return len(covered) / len(universe) if universe else 1.0

    @property
    def full_l2(self) -> bool:
        return self.covered_l2 >= self.universe_l2

    def observe(
        self,
        draw: RandomDraw,
        footprint: Mapping[str, Iterable[Any]],
        *,
        question_text: str = "",
        question_text_hash: str = "",
    ) -> Dict[str, int]:
        before = {
            level: len(getattr(self, f"covered_{level}"))
            for level in ("l0", "l1", "l2")
        }
        for level in ("l0", "l1", "l2"):
            raw_values = footprint.get(level, ())
            # Random full-coverage can make millions of repeated draws.  Its
            # plan footprints are immutable, so callers may pass frozensets
            # and avoid rebuilding the same set on every draw.
            values = (
                raw_values
                if isinstance(raw_values, (set, frozenset))
                else _as_set(raw_values)
            )
            universe = getattr(self, f"universe_{level}")
            getattr(self, f"covered_{level}").update(values & universe)

        self.draws += 1
        self.gap_counts[draw.gap_id] += 1
        self.plan_counts[draw.plan_id] += 1
        if question_text_hash:
            self.text_counts[question_text_hash] += 1
        elif question_text:
            self.text_counts[hashlib.sha256(question_text.encode("utf-8")).hexdigest()] += 1

        gain = {
            level: len(getattr(self, f"covered_{level}")) - before[level]
            for level in ("l0", "l1", "l2")
        }
        if not any(gain.values()):
            self.no_gain_draws += 1
        for level in ("l0", "l1", "l2"):
            self.coverage_rate_sums[level] += self.rate(level)
            self.cumulative_gains[level] += gain[level]
        self._record_milestones()
        return gain

    def _record_milestones(self) -> None:
        for level in ("l0", "l1", "l2"):
            level_marks = self.milestones.setdefault(level, {})
            rate = self.rate(level)
            for threshold in MILESTONES:
                key = f"{int(threshold * 100)}"
                if key not in level_marks and rate >= threshold:
                    level_marks[key] = self.draws

    def state_dict(self) -> Dict[str, Any]:
        return {
            "schema": "rq2_random_coverage_accumulator_v1",
            "universe": {
                level: sorted(getattr(self, f"universe_{level}"))
                for level in ("l0", "l1", "l2")
            },
            "covered": {
                level: sorted(getattr(self, f"covered_{level}"))
                for level in ("l0", "l1", "l2")
            },
            "draws": self.draws,
            "no_gain_draws": self.no_gain_draws,
            "gap_counts": dict(self.gap_counts),
            "plan_counts": dict(self.plan_counts),
            "text_counts": dict(self.text_counts),
            "milestones": self.milestones,
            "coverage_rate_sums": self.coverage_rate_sums,
            "cumulative_gains": self.cumulative_gains,
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        if state.get("schema") != "rq2_random_coverage_accumulator_v1":
            raise ValueError("Unsupported coverage checkpoint schema")
        checkpoint_universe = state.get("universe") or {}
        for level in ("l0", "l1", "l2"):
            if _as_set(checkpoint_universe.get(level, [])) != getattr(
                self, f"universe_{level}"
            ):
                raise ValueError(f"{level.upper()} universe changed since checkpoint")
            setattr(
                self,
                f"covered_{level}",
                _as_set((state.get("covered") or {}).get(level, [])),
            )
        self._validate_coverage()
        self.draws = int(state.get("draws", 0))
        self.no_gain_draws = int(state.get("no_gain_draws", 0))
        self.gap_counts = Counter(
            {str(key): int(value) for key, value in (state.get("gap_counts") or {}).items()}
        )
        self.plan_counts = Counter(
            {str(key): int(value) for key, value in (state.get("plan_counts") or {}).items()}
        )
        self.text_counts = Counter(
            {str(key): int(value) for key, value in (state.get("text_counts") or {}).items()}
        )
        self.milestones = {
            str(level): {str(key): int(value) for key, value in marks.items()}
            for level, marks in (state.get("milestones") or {}).items()
        }
        self.coverage_rate_sums = {
            level: float((state.get("coverage_rate_sums") or {}).get(level, 0.0))
            for level in ("l0", "l1", "l2")
        }
        self.cumulative_gains = {
            level: int((state.get("cumulative_gains") or {}).get(level, 0))
            for level in ("l0", "l1", "l2")
        }

    @staticmethod
    def _duplicate_count(counter: Counter[str]) -> int:
        return sum(max(count - 1, 0) for count in counter.values())

    def summary(self) -> Dict[str, Any]:
        draws = max(self.draws, 1)
        coverage = {}
        for level in ("l0", "l1", "l2"):
            universe = getattr(self, f"universe_{level}")
            covered = getattr(self, f"covered_{level}")
            coverage[level] = {
                "covered": len(covered),
                "total": len(universe),
                "rate": self.rate(level),
                "auc_over_draws": self.coverage_rate_sums[level] / draws,
                "new_coverage": self.cumulative_gains[level],
                "new_coverage_per_question": self.cumulative_gains[level] / draws,
            }
        l2_marks = self.milestones.get("l2", {})
        return {
            "schema": "rq2_random_full_coverage_summary_v1",
            "draws": self.draws,
            "full_l2": self.full_l2,
            "coverage": coverage,
            "milestones": self.milestones,
            "no_gain_draws": self.no_gain_draws,
            "no_gain_rate": self.no_gain_draws / draws,
            "gap_duplicate_count": self._duplicate_count(self.gap_counts),
            "gap_duplicate_rate": self._duplicate_count(self.gap_counts) / draws,
            "plan_duplicate_count": self._duplicate_count(self.plan_counts),
            "plan_duplicate_rate": self._duplicate_count(self.plan_counts) / draws,
            "text_duplicate_count": self._duplicate_count(self.text_counts),
            "text_duplicate_rate": self._duplicate_count(self.text_counts) / draws,
            "unique_gaps_drawn": len(self.gap_counts),
            "unique_plans_drawn": len(self.plan_counts),
            "unique_texts": len(self.text_counts),
            "l2_tail_questions_95_to_100": (
                l2_marks["100"] - l2_marks["95"]
                if "100" in l2_marks and "95" in l2_marks
                else None
            ),
        }


def write_checkpoint(
    path: Path,
    *,
    selector: StaticRandomSelector,
    accumulator: CoverageAccumulator,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    payload = {
        "schema": "rq2_random_full_coverage_checkpoint_v1",
        "selector": selector.state_dict(),
        "coverage": accumulator.state_dict(),
        "metadata": dict(metadata or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def load_checkpoint(
    path: Path,
    *,
    selector: StaticRandomSelector,
    accumulator: CoverageAccumulator,
) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "rq2_random_full_coverage_checkpoint_v1":
        raise ValueError("Unsupported random full-coverage checkpoint schema")
    selector.load_state_dict(payload["selector"])
    accumulator.load_state_dict(payload["coverage"])
    if selector.draw_count != accumulator.draws:
        raise ValueError("Selector and coverage draw counts disagree")
    return dict(payload.get("metadata") or {})


def run_until_full(
    *,
    selector: StaticRandomSelector,
    accumulator: CoverageAccumulator,
    realize: Callable[[RandomDraw, int], Mapping[str, Any]],
    on_draw: Callable[[RandomDraw, Mapping[str, Any], Mapping[str, int]], None] | None = None,
    checkpoint_path: Path | None = None,
    checkpoint_interval: int = 1000,
    max_draws: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run independent random draws until L2 is full.

    ``max_draws`` is a testing/watchdog boundary.  Reaching it does not produce
    a successful full-coverage result.
    """
    if checkpoint_interval < 1:
        raise ValueError("checkpoint_interval must be positive")
    while not accumulator.full_l2:
        if max_draws is not None and accumulator.draws >= max_draws:
            raise RuntimeError(
                f"Random full-coverage watchdog reached at {max_draws} draws"
            )
        draw = selector.draw()
        record = realize(draw, accumulator.draws + 1)
        footprint = record.get("coverage_footprint") or {}
        gain = accumulator.observe(
            draw,
            footprint,
            question_text=str(record.get("question") or ""),
            question_text_hash=str(record.get("question_text_hash") or ""),
        )
        if on_draw is not None:
            on_draw(draw, record, gain)
        if checkpoint_path and accumulator.draws % checkpoint_interval == 0:
            write_checkpoint(
                checkpoint_path,
                selector=selector,
                accumulator=accumulator,
                metadata=metadata,
            )
    if checkpoint_path:
        write_checkpoint(
            checkpoint_path,
            selector=selector,
            accumulator=accumulator,
            metadata=metadata,
        )
    return accumulator.summary()


def run_fixed_budget(
    *,
    selector: StaticRandomSelector,
    accumulator: CoverageAccumulator,
    realize: Callable[[RandomDraw, int], Mapping[str, Any]],
    question_budget: int,
    checkpoint_path: Path | None = None,
    checkpoint_interval: int = 1000,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Run coverage-blind random draws for exactly ``question_budget`` calls.

    This is intentionally separate from ``run_until_full``: a budget-matched
    comparison must finish successfully even when its L2 universe remains
    uncovered.
    """
    if question_budget < 1:
        raise ValueError("question_budget must be positive")
    if checkpoint_interval < 1:
        raise ValueError("checkpoint_interval must be positive")
    while accumulator.draws < question_budget:
        draw = selector.draw()
        record = realize(draw, accumulator.draws + 1)
        accumulator.observe(
            draw,
            record.get("coverage_footprint") or {},
            question_text=str(record.get("question") or ""),
            question_text_hash=str(record.get("question_text_hash") or ""),
        )
        if checkpoint_path and accumulator.draws % checkpoint_interval == 0:
            write_checkpoint(
                checkpoint_path,
                selector=selector,
                accumulator=accumulator,
                metadata=metadata,
            )
    if checkpoint_path:
        write_checkpoint(
            checkpoint_path,
            selector=selector,
            accumulator=accumulator,
            metadata=metadata,
        )
    summary = accumulator.summary()
    summary["question_budget"] = question_budget
    summary["budget_exhausted"] = True
    return summary
