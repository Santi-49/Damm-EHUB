// Plan optimise endpoint — request / response shapes.
//
// Both the CSV flow (client-side parsed) and the manual flow send the same
// PlanOptimizeRequest JSON body. The response drives the SequenceGraph.

import type { Line } from './linewise'

export interface PlanProduct {
  sku_id: string
  quantity_units: number
}

export interface PlanOptimizeRequest {
  products: PlanProduct[]
}

export interface PlanGraphNode {
  id: string
  /** Short display label shown on the node */
  label: string
  line_id: Line
  /** SKU family — used for fill colour, matches Gantt palette */
  family: string
  /** Production volume in hl — drives node size */
  volume_hl: number
}

export interface PlanGraphEdge {
  id: string
  source: string
  target: string
  /** Changeover hours for this transition */
  hours: number
  /** 'opt' = LineWise proposed path · 'baseline' = JDA / S_real order */
  path: 'opt' | 'baseline'
}

export interface PlanOptimizeResponse {
  nodes: PlanGraphNode[]
  edges: PlanGraphEdge[]
  /** Max total hours across all lines (makespan) */
  makespan_h: number
  /** Changeover hours saved vs naive / baseline ordering */
  h_saved: number
  /** Fraction of demand covered [0–1] */
  coverage_pct: number
  /** SKU ids that were dropped under capacity */
  dropped_skus: string[]
}
