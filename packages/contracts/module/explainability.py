"""LineWise explainability contract — structured facts for the chat surface.

Everything in this module is **data**, never prose. The chat surface (see
``chat.py``) is a fully LLM-powered conversation; it grounds its
natural-language replies on an :class:`ExplanationPack` produced once per
optimiser solution. If a fact is not in the pack, the assistant must say it
doesn't know — never invent.

Four levels of explainability are exposed, in order of granularity:

  1. **Solution** — headline KPIs, bottleneck, decision themes
  2. **Line**     — per-line rationale (assignment, sequence cost, bottleneck)
  3. **Slot**     — per-slot facts + per-transition drivers (SHAP-style)
  4. **Counterfactual** — for every non-trivial choice, the next-best
                          alternative and why it lost

The contract is **tiered**. The "minimum viable pack" the backend MUST ship
on day 1 is:

  * ``solution.headline``
  * ``solution.bottleneck``
  * ``lines``                (per-line metrics)
  * ``slots``                (one entry per slot in the sequence)
  * ``transitions``          (one entry per changeover slot; drivers may be empty)

Everything else (``baseline_delta``, ``themes``, ``counterfactuals``,
``dropped_skus``, ``rationale_tags``, ``drivers``) is optional and can be
added in later tiers without breaking the frontend. The LLM degrades
gracefully — if it can't find a fact, it says so.

Trivial decisions dominated by hard constraints (e.g. format gate) are
encoded as ``rationale_tags`` on the slot. Counterfactuals are reserved for
choices the solver actively scored and rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Mapping, Protocol

from .schemas import (
    ChangeoverSegment,
    EdgeSource,
    Format,
    LineId,
    OptimizerInput,
    OptimizerOutput,
    SimulationReport,
    SlotType,
)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

DecisionKind = Literal[
    "line_assignment",      # which line a SKU lands on
    "sequence_position",    # where in the line's ordering it goes
    "drop_or_keep",         # is the SKU produced or dropped under capacity
    "calendar_placement",   # cleaning / maintenance slot positioning
]

ThemeKind = Literal[
    "consolidated_format",  # grouped same-format SKUs to avoid container changes
    "avoided_brand_flip",   # ordered to skip an expensive brand changeover
    "reassigned_sku",       # moved SKU off the line it ran on in baseline
    "dropped_sku",          # dropped under capacity pressure
    "exploited_slack",      # filled an otherwise idle window on a line
    "respected_calendar",   # placement driven by cleaning / maintenance window
]

TransitionVsBaseline = Literal[
    "new",                  # this transition does not exist in the baseline
    "kept",                 # same pair appears in baseline with similar cost
    "improved",             # same pair appears in baseline but optimiser is faster
    "avoided_in_opt",       # baseline had this transition, optimiser eliminated it
]

GroundingKind = Literal[
    "solution",
    "line",
    "theme",
    "slot",
    "transition",
    "counterfactual",
    "dropped_sku",
]


# ---------------------------------------------------------------------------
# Level 1 — solution-wide facts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HeadlineKpis:
    """Top-line numbers for the whole solution. Required (tier 1)."""

    makespan_hours: float
    productive_hours: float
    changeover_hours: float
    n_changeovers: int
    coverage_pct: float
    dropped_sku_count: int
    margin_lost_eur: float
    oee_weighted_global: float


@dataclass(frozen=True)
class BaselineDelta:
    """How the optimiser solution compares to a baseline (typically S_real).

    Optional (tier 2) — set only when a baseline simulation is available.
    All deltas are signed *in favour of the optimiser*: positive means the
    optimiser is better.
    """

    baseline_label: str                          # e.g. "S_real (executed week 18-24 May 2026)"
    makespan_hours_saved: float
    changeover_hours_saved: float
    productive_hours_gained: float
    coverage_delta_pct: float
    oee_delta_pp: float                          # percentage points
    n_changeovers_avoided: int


@dataclass(frozen=True)
class BottleneckFact:
    """Which line drives makespan and by how much. Required (tier 1)."""

    line_id: LineId
    makespan_hours: float
    slack_vs_next_line_hours: float              # how far ahead of the next-busiest line
    primary_cost_driver: Literal[
        "productive",
        "changeover",
        "cleaning",
        "maintenance",
        "incidents",
    ]


@dataclass(frozen=True)
class DecisionTheme:
    """A high-level decision pattern the optimiser materialised. Optional (tier 2).

    Themes are the canonical hooks the LLM uses to narrate the solution.
    When present in :class:`SolutionExplanation`, ordered by ``impact_hours``
    descending.
    """

    theme_id: str
    kind: ThemeKind
    affected_line_ids: tuple[LineId, ...]
    affected_sku_ids: tuple[str, ...]
    impact_hours: float | None = None
    impact_eur: float | None = None
    related_slot_ids: tuple[str, ...] = ()
    related_transition_ids: tuple[str, ...] = ()
    rationale_tags: tuple[str, ...] = ()         # structured tags, not prose


@dataclass(frozen=True)
class SolutionExplanation:
    headline: HeadlineKpis                       # required
    bottleneck: BottleneckFact                   # required
    baseline_delta: BaselineDelta | None = None  # tier 2
    objective_components: Mapping[str, float] = field(default_factory=dict)  # tier 2
    themes: tuple[DecisionTheme, ...] = ()       # tier 2


# ---------------------------------------------------------------------------
# Level 2 — line-level facts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineExplanation:
    """Required (tier 1). Baseline fields and rationale tags are tier 2."""

    line_id: LineId
    n_skus_assigned: int
    allowed_formats: tuple[Format, ...]
    formats_used: tuple[Format, ...]
    capacity_used_hours: float
    capacity_available_hours: float              # window length - forced events
    is_bottleneck: bool
    productive_hours: float
    changeover_hours: float
    changeover_ratio: float                      # changeover / (productive + changeover)
    baseline_changeover_hours: float | None = None       # tier 2
    baseline_productive_hours: float | None = None       # tier 2
    rationale_tags: tuple[str, ...] = ()                  # tier 2


# ---------------------------------------------------------------------------
# Level 3 — slot-level facts (slot + transition)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangeoverDriverFact:
    """SHAP-style per-feature contribution to a changeover's predicted time."""

    feature: str                                 # ChangeoverSegment name, or any ML feature
    contribution_hours: float


@dataclass(frozen=True)
class TransitionExplanation:
    """A changeover edge between two consecutive slots on the same line.

    Required (tier 1) — one entry per ``slot_type == "cambio"`` in the
    sequence. ``drivers`` may be empty until the ML model is producing
    attributions; ``vs_baseline`` is tier 2.
    """

    transition_id: str                           # stable id, e.g. f"{line_id}:{from_slot_id}->{to_slot_id}"
    line_id: LineId
    from_slot_id: str
    to_slot_id: str
    from_sku_id: str
    to_sku_id: str
    total_hours: float
    segments: Mapping[ChangeoverSegment, float]
    source: EdgeSource
    drivers: tuple[ChangeoverDriverFact, ...] = ()       # tier 2
    vs_baseline: TransitionVsBaseline | None = None      # tier 2
    hours_saved_vs_baseline: float | None = None         # tier 2


@dataclass(frozen=True)
class SlotExplanation:
    """Per-slot rationale. References slot by id — does NOT duplicate slot
    geometry (start/end/units) which already lives in the :class:`Sequence`.

    Required (tier 1). ``rationale_tags`` are tier 2.
    """

    slot_id: str
    line_id: LineId
    slot_type: SlotType
    sku_id: str | None = None
    expected_speed_uds_per_hour: float | None = None
    expected_oee: float | None = None
    transition_id: str | None = None             # set when slot_type == "cambio"
    rationale_tags: tuple[str, ...] = ()         # tier 2


# ---------------------------------------------------------------------------
# Level 4 — counterfactuals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Counterfactual:
    """For a non-trivial optimiser decision, the next-best alternative and why
    it lost. Optional (tier 3) — the hardest fact class to produce.

    A counterfactual exists when the alternative was actually *evaluated* by
    the solver and rejected on a score. Trivial choices fully dominated by
    hard constraints (format gate, calendar lock) live as ``rationale_tags``
    on the slot instead.
    """

    counterfactual_id: str
    decision_kind: DecisionKind
    chosen_label: str                            # e.g. "L19", "after SKU-A", "drop SKU-Y"
    chosen_cost_hours: float
    alternative_label: str
    alternative_cost_hours: float
    blocking_reasons: tuple[str, ...]            # structured tags, e.g. ("format_mismatch",)
    extra_cost_hours: float | None = None        # alt_cost - chosen_cost; None if hard-blocked
    related_slot_ids: tuple[str, ...] = ()
    related_sku_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DroppedSkuExplanation:
    """Why a SKU was not produced under the chosen objective. Optional (tier 2)."""

    sku_id: str
    units_demanded: int
    units_dropped: int
    margin_eur_per_unit: float
    margin_lost_eur: float
    rationale_tags: tuple[str, ...] = ()         # e.g. ("lowest_margin_in_window",)
    capacity_shortfall_hours: float | None = None
    eligible_line_ids: tuple[LineId, ...] = ()


# ---------------------------------------------------------------------------
# Pack + contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExplanationPack:
    """Full structured-fact bundle for a single optimiser solution.

    Produced once by an :class:`ExplainerContract` implementation and shipped
    to the frontend alongside the :class:`Sequence` + :class:`SimulationReport`.
    The chat backend uses it as grounding context for the LLM.

    **Tiering** (what the backend MUST ship vs MAY ship):

    Tier 1 (minimum viable):
        * ``solution.headline``, ``solution.bottleneck``
        * one ``LineExplanation`` per line in scope
        * one ``SlotExplanation`` per slot in the sequence
        * one ``TransitionExplanation`` per changeover slot (``drivers`` may be empty)

    Tier 2 (rich):
        * ``solution.baseline_delta``, ``solution.themes``
        * ``LineExplanation.baseline_*`` and ``rationale_tags``
        * ``TransitionExplanation.drivers`` (once ML attribution is wired up)
        * ``TransitionExplanation.vs_baseline`` and ``hours_saved_vs_baseline``
        * ``dropped_skus``

    Tier 3 (counterfactuals):
        * ``counterfactuals`` — requires solver-internal scoring or re-solve

    Invariants the implementation MUST maintain:

    * Every ``slot_id`` referenced by ``transitions`` / ``counterfactuals`` /
      ``themes`` appears in ``slots``.
    * Every ``sku_id`` referenced is a valid SKU in the optimiser input.
    * ``solution.headline`` agrees with the source ``SimulationReport`` to
      two decimal places — no drift between KPIs and facts.
    """

    solution_id: str
    window_start: date
    window_end: date
    solution: SolutionExplanation
    lines: tuple[LineExplanation, ...]
    slots: tuple[SlotExplanation, ...]
    transitions: tuple[TransitionExplanation, ...]
    counterfactuals: tuple[Counterfactual, ...] = ()         # tier 3
    dropped_skus: tuple[DroppedSkuExplanation, ...] = ()     # tier 2


class ExplainerContract(Protocol):
    """Builds an :class:`ExplanationPack` from optimiser + simulator outputs.

    Implementations may consult:

    * ``OptimizerInput`` — for capability, calendar and per-SKU margin lookups
      used to fill ``rationale_tags`` and ``DroppedSkuExplanation.eligible_line_ids``.
    * ``OptimizerOutput`` — for the chosen sequence, dropouts and (optionally)
      the solver log used to extract counterfactual alternatives.
    * ``SimulationReport`` for the optimised sequence — to anchor headline KPIs.
    * An optional baseline ``SimulationReport`` (typically ``S_real``) — required
      to populate ``BaselineDelta`` and ``TransitionExplanation.vs_baseline``.

    The function is deterministic given identical inputs: same solution →
    same pack. No LLM calls happen here; this is the structured layer only.
    """

    async def build_pack(
        self,
        *,
        solution_id: str,
        optimizer_input: OptimizerInput,
        optimizer_output: OptimizerOutput,
        simulation_opt: SimulationReport,
        simulation_baseline: SimulationReport | None = None,
        baseline_label: str = "S_real",
    ) -> ExplanationPack:
        ...
