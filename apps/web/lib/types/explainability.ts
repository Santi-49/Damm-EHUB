// Explainability domain types — mirrors packages/contracts/module/explainability.py
//
// All snake_case to match the wire format. These types describe the
// structured fact pack the backend produces once per optimiser solution; the
// chat surface (see chat.ts) is grounded on this pack.
//
// The contract is tiered. Tier 1 (minimum) fields are required by the type
// system; tier 2/3 (advanced) fields are optional so the backend can ship
// incrementally without breaking the frontend.

import type { ChangeoverSegment, EdgeSource, Format, Line, SlotKind } from './linewise'

// ---------------------------------------------------------------------------
// Type aliases
// ---------------------------------------------------------------------------

export type DecisionKind =
  | 'line_assignment'
  | 'sequence_position'
  | 'drop_or_keep'
  | 'calendar_placement'

export type ThemeKind =
  | 'consolidated_format'
  | 'avoided_brand_flip'
  | 'reassigned_sku'
  | 'dropped_sku'
  | 'exploited_slack'
  | 'respected_calendar'

export type TransitionVsBaseline = 'new' | 'kept' | 'improved' | 'avoided_in_opt'

export type GroundingKind =
  | 'solution'
  | 'line'
  | 'theme'
  | 'slot'
  | 'transition'
  | 'counterfactual'
  | 'dropped_sku'

// ---------------------------------------------------------------------------
// Level 1 — solution-wide facts
// ---------------------------------------------------------------------------

export interface HeadlineKpis {
  makespan_hours: number
  productive_hours: number
  changeover_hours: number
  n_changeovers: number
  coverage_pct: number
  dropped_sku_count: number
  margin_lost_eur: number
  oee_weighted_global: number
}

/** Tier 2 — set only when a baseline simulation is available. Positive deltas favour the optimiser. */
export interface BaselineDelta {
  baseline_label: string
  makespan_hours_saved: number
  changeover_hours_saved: number
  productive_hours_gained: number
  coverage_delta_pct: number
  oee_delta_pp: number
  n_changeovers_avoided: number
}

export interface BottleneckFact {
  line_id: Line
  makespan_hours: number
  slack_vs_next_line_hours: number
  primary_cost_driver: 'productive' | 'changeover' | 'cleaning' | 'maintenance' | 'incidents'
}

/** Tier 2 — high-level decision pattern. When present in SolutionExplanation, ordered by impact_hours desc. */
export interface DecisionTheme {
  theme_id: string
  kind: ThemeKind
  affected_line_ids: Line[]
  affected_sku_ids: string[]
  impact_hours?: number
  impact_eur?: number
  related_slot_ids?: string[]
  related_transition_ids?: string[]
  rationale_tags?: string[]
}

export interface SolutionExplanation {
  headline: HeadlineKpis
  bottleneck: BottleneckFact
  /** Tier 2 */
  baseline_delta?: BaselineDelta
  /** Tier 2 — solver objective term contributions, e.g. {"makespan": 47.0, "lambda_changeover": 12.0} */
  objective_components?: Record<string, number>
  /** Tier 2 */
  themes?: DecisionTheme[]
}

// ---------------------------------------------------------------------------
// Level 2 — line-level facts
// ---------------------------------------------------------------------------

export interface LineExplanation {
  line_id: Line
  n_skus_assigned: number
  allowed_formats: Format[]
  formats_used: Format[]
  capacity_used_hours: number
  capacity_available_hours: number
  is_bottleneck: boolean
  productive_hours: number
  changeover_hours: number
  /** changeover / (productive + changeover) */
  changeover_ratio: number
  /** Tier 2 */
  baseline_changeover_hours?: number
  /** Tier 2 */
  baseline_productive_hours?: number
  /** Tier 2 */
  rationale_tags?: string[]
}

// ---------------------------------------------------------------------------
// Level 3 — slot-level facts (slot + transition)
// ---------------------------------------------------------------------------

/** SHAP-style per-feature contribution to a changeover's predicted time. */
export interface ChangeoverDriverFact {
  feature: string
  contribution_hours: number
}

/** One per changeover slot in the sequence. Tier 1; drivers and baseline fields are tier 2. */
export interface TransitionExplanation {
  /** Stable id, e.g. `${line_id}:${from_slot_id}->${to_slot_id}` */
  transition_id: string
  line_id: Line
  from_slot_id: string
  to_slot_id: string
  from_sku_id: string
  to_sku_id: string
  total_hours: number
  segments: Partial<Record<ChangeoverSegment, number>>
  source: EdgeSource
  /** Tier 2 */
  drivers?: ChangeoverDriverFact[]
  /** Tier 2 */
  vs_baseline?: TransitionVsBaseline
  /** Tier 2 — positive means the optimiser is faster on this transition */
  hours_saved_vs_baseline?: number
}

/** One entry per slot in the sequence. References the slot by id — does not duplicate slot geometry. */
export interface SlotExplanation {
  slot_id: string
  line_id: Line
  slot_type: SlotKind
  sku_id?: string
  expected_speed_uds_per_hour?: number
  expected_oee?: number
  /** Set when slot_type === 'changeover' */
  transition_id?: string
  /** Tier 2 */
  rationale_tags?: string[]
}

// ---------------------------------------------------------------------------
// Level 4 — counterfactuals
// ---------------------------------------------------------------------------

/**
 * Tier 3 — the next-best alternative the solver evaluated and rejected.
 * Trivial decisions fully dominated by hard constraints (e.g. format gate)
 * live as `rationale_tags` on the slot instead.
 */
export interface Counterfactual {
  counterfactual_id: string
  decision_kind: DecisionKind
  /** e.g. "L19", "after SKU-A", "drop SKU-Y" */
  chosen_label: string
  chosen_cost_hours: number
  alternative_label: string
  alternative_cost_hours: number
  /** Structured tags, e.g. ["format_mismatch"] */
  blocking_reasons: string[]
  /** alternative_cost_hours - chosen_cost_hours; null/undefined if hard-blocked */
  extra_cost_hours?: number
  related_slot_ids?: string[]
  related_sku_ids?: string[]
}

/** Tier 2 — why a demand SKU was not produced under the chosen objective. */
export interface DroppedSkuExplanation {
  sku_id: string
  units_demanded: number
  units_dropped: number
  margin_eur_per_unit: number
  margin_lost_eur: number
  rationale_tags?: string[]
  capacity_shortfall_hours?: number
  eligible_line_ids?: Line[]
}

// ---------------------------------------------------------------------------
// Pack
// ---------------------------------------------------------------------------

/**
 * Full structured-fact bundle for a single optimiser solution. Shipped to the
 * frontend alongside the Sequence + SimulationReport. The chat backend uses it
 * as grounding context for the LLM.
 *
 * Tiering: see explainability.py for the authoritative spec.
 *   Tier 1 (must ship): solution.headline, solution.bottleneck, lines, slots, transitions
 *   Tier 2 (rich):       baseline_delta, themes, drivers, dropped_skus, rationale_tags
 *   Tier 3 (CFs):        counterfactuals
 */
export interface ExplanationPack {
  solution_id: string
  /** ISO date */
  window_start: string
  /** ISO date */
  window_end: string
  solution: SolutionExplanation
  lines: LineExplanation[]
  slots: SlotExplanation[]
  transitions: TransitionExplanation[]
  /** Tier 3 */
  counterfactuals?: Counterfactual[]
  /** Tier 2 */
  dropped_skus?: DroppedSkuExplanation[]
}
