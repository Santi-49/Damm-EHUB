// Domain types — mirrors packages/contracts/module/schemas.py

export type Line = 14 | 17 | 19

export type SlotKind = 'production' | 'changeover' | 'cleaning' | 'maintenance'

/** Can formats: 50 cl (1/2), 33 cl (1/3), 44 cl (2/5). */
export type Format = '1/2' | '1/3' | '2/5'

/** Provenance of a changeover edge weight. */
export type EdgeSource = 'teorico' | 'empirico' | 'hibrido' | 'ml'

/** Decomposition of a total changeover into its driving segments. */
export type ChangeoverSegment =
  | 'brand'
  | 'container'
  | 'cap'
  | 'primary_pack'
  | 'secondary_pack'
  | 'pallet'
  | 'product'
  | 'volume'
  | 'startup'
  | 'shutdown'

export interface Slot {
  id: string
  line: Line
  /** ISO timestamp */
  start: string
  end: string
  kind: SlotKind
  sku?: string
  /** Display label: SKU code + family */
  label?: string
  units?: number
  /** Expected OEE for this slot [0–1] */
  oee_expected?: number
  /** Actual OEE from S_real, only on real sequence */
  oee_actual?: number
  /** Hours of changeover time (for changeover slots) */
  changeover_h?: number
  /** Whether changeover edge came from ML or theoretical matrix */
  changeover_source?: 'ml' | 'hibrido' | 'teorico'
  /** SHAP-style top features driving changeover time */
  changeover_drivers?: ChangeoverDriver[]
  /** True when this production slot was injected by an urgent-demand replan. */
  is_urgent?: boolean
}

export interface ChangeoverDriver {
  feature: string
  impact_h: number
}

export interface Sequence {
  id: string
  week_id: string
  week_start: string
  week_end: string
  source: 'opt' | 'real' | 'replan'
  slots: Slot[]
}

export interface LineMetrics {
  line: Line
  oee: number
  h_productive: number
  h_changeover: number
  h_cleaning: number
  h_maintenance: number
  h_idle: number
  coverage: number
}

export interface SimulationReport {
  sequence_id: string
  oee_global: number
  oee_per_line: LineMetrics[]
  h_changes: number
  h_productive: number
  coverage: number
  /** Total wall-clock hours from first to last slot */
  makespan_h: number
  dropped_skus: DroppedSku[]
}

export interface DroppedSku {
  sku: string
  units_demanded: number
  units_dropped: number
  margin_lost: number
  reason: string
}

export interface Inefficiency {
  id: string
  from_sku: string
  to_sku: string
  line: Line
  /** Average observed changeover time (hours) */
  avg_changeover_h: number
  /** Theoretical / expected changeover time (hours) */
  theoretical_h: number
  /** Extra hours lost beyond theoretical */
  avg_loss_h: number
  n_occurrences: number
  /** Human-readable explanation */
  reason: string
  /** Example week where this was worst */
  example_week?: string
}

export interface DeltaMetrics {
  oee_pp: number              // percentage-point delta (opt − real)
  h_changes_saved: number
  h_productive_gained: number
  coverage_delta: number
}

export type PerturbationKind = 'urgent_demand' | 'breakdown' | 'maintenance_shift'

export interface UrgentDemandPayload {
  sku: string
  units: number
  due_day: string
  priority: 'high' | 'medium'
}

export interface BreakdownPayload {
  line: Line
  start: string
  duration_h: number
}

export interface MaintenanceShiftPayload {
  line: Line
  original_day: string
  new_day: string
  duration_h: number
}

export interface Perturbation {
  kind: PerturbationKind
  payload: UrgentDemandPayload | BreakdownPayload | MaintenanceShiftPayload
}

export interface ReplanResult {
  sequence: Sequence
  simulation: SimulationReport
  dropped_skus: DroppedSku[]
}

export interface SkuMaster {
  sku: string
  family: string
  format: '1/2' | '1/3' | '2/5'
  brand: string
  margin_eur_per_unit: number
}
