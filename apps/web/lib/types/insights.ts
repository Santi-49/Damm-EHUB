// Domain types for the Insights view — the optimizer v2 replay benchmark.
// Mirrors a future Pydantic schema in services/api/app/schemas/linewise.py.

export interface WeekImpact {
  week_id: string                         // e.g. "2025-W14-7d"
  week_start: string                      // ISO date — Monday
  week_end: string                        // ISO date — Sunday
  node_count: number                      // planning graph demand nodes
  v2_makespan_h: number                   // optimized makespan
  real_simulated_makespan_h: number       // real simulated node + inefficiency + edge makespan
  clean_saving_h: number                  // real_simulated_makespan_h - v2_makespan_h
  adjusted_saving_h: number               // line-specific cleaning + inefficiency replay
  maintenance_adjusted_saving_h: number   // adjusted_saving_h plus maintenance / rerun replay
  mixed_observed_saving_h: number         // real WO total + edge vs adjusted v2
  real_cleaning_h: number                 // historical cleaning WO load
  real_maintenance_rerun_h: number        // historical maintenance / rerun load
  has_production: boolean
}

export interface ImpactAtlas {
  year: number
  source_dataset: string
  generated_at: string
  weeks: WeekImpact[]
  windows_evaluated: number
  valid_solutions: number
  mean_v2_makespan_h: number
  mean_real_simulated_makespan_h: number
  clean_saving_h_per_week: number
  adjusted_saving_h_per_week: number
  adjusted_weeks_won: number
  maintenance_adjusted_saving_h_per_week: number
  maintenance_adjusted_weeks_won: number
  mixed_observed_saving_h_per_week: number
  mixed_observed_weeks_won: number
  mean_real_cleaning_h: number
  mean_real_maintenance_rerun_h: number
}
