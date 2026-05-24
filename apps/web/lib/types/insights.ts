// Domain types for the Insights view — the 2025 counterfactual leaderboard.
// Mirrors a future Pydantic schema in services/api/app/schemas/linewise.py.

export interface WeekImpact {
  week_id: string                  // e.g. "2025-W14"
  week_start: string               // ISO date — Monday
  week_end: string                 // ISO date — Sunday
  hours_recovered: number          // changeover hours LineWise would save vs S_real
  margin_recovered: number         // € from SKUs LineWise would not have dropped
  dropped_skus_recovered: number   // count of SKUs LineWise would have kept
  oee_uplift_pp: number            // OEE percentage points uplift
  real_oee: number                 // historical OEE for context (0–1)
  has_production: boolean          // false = vacation / cleaning-only week
}

export interface ImpactAtlas {
  year: number
  weeks: WeekImpact[]              // always 52 entries, in week order
  total_hours_recovered: number
  total_margin_recovered: number
  total_dropped_skus_recovered: number
  weeks_with_production: number
  avg_oee_uplift_pp: number
}
