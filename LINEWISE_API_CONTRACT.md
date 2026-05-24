# LineWise API Contract

This file documents the backend responses expected by `apps/web/lib/linewise-api.ts`.

Base URL is controlled by the frontend env var:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

All endpoints below are relative to that base URL and should therefore live under:

```text
/api/v1/linewise/*
```

The frontend already falls back to mock fixtures when these endpoints are missing, so the backend can implement them incrementally.

## Shared Rules

- JSON only.
- Auth should follow the existing API pattern: `Authorization: Bearer <access_token>`.
- Use `snake_case` field names.
- Dates/timestamps should be ISO strings.
- Percentages are fractions in `[0, 1]`, not `0-100`, unless a field explicitly says `pp`.
- Line IDs are numeric: `14`, `17`, `19`.

## 1. List Comparable Weeks

```http
GET /linewise/weeks
```

Returns week options the user can choose in Compare.

### Response

```ts
type WeekOption = {
  id: string
  label: string
  range: string
  source: 'demo' | 'historical'
  reason: string
  productionRows?: number
  skuCount?: number
  units?: number
  avgOee?: number
  downtimeH?: number
}
```

### Example

```json
[
  {
    "id": "2025-W30",
    "label": "2025-W30 · high SKU variety",
    "range": "21–27 Jul 2025",
    "source": "historical",
    "reason": "50 production WOs across 46 SKUs. Good stress test for sequencing complexity.",
    "productionRows": 50,
    "skuCount": 46,
    "units": 15855686,
    "avgOee": 0.521,
    "downtimeH": 207.4
  }
]
```

## 2. Compare Real vs LineWise

```http
GET /linewise/compare?week_id=2025-W30
```

Returns everything the Compare page needs in one bundle.

### Response

```ts
type CompareBundle = {
  week: WeekOption
  solution_id: string
  real_sequence: Sequence
  opt_sequence: Sequence
  real_simulation: SimulationReport
  opt_simulation: SimulationReport
  delta: DeltaMetrics
}
```

### Sequence

```ts
type Sequence = {
  id: string
  week_id: string
  week_start: string
  week_end: string
  source: 'opt' | 'real' | 'replan'
  slots: Slot[]
}

type Slot = {
  id: string
  line: 14 | 17 | 19
  start: string
  end: string
  kind: 'production' | 'changeover' | 'cleaning' | 'maintenance'
  sku?: string
  label?: string
  units?: number
  oee_expected?: number
  oee_actual?: number
  changeover_h?: number
  changeover_source?: 'ml' | 'hibrido' | 'teorico'
  changeover_drivers?: ChangeoverDriver[]
}

type ChangeoverDriver = {
  feature: string
  impact_h: number
}
```

### SimulationReport

```ts
type SimulationReport = {
  sequence_id: string
  oee_global: number
  oee_per_line: LineMetrics[]
  h_changes: number
  h_productive: number
  coverage: number
  makespan_h: number
  dropped_skus: DroppedSku[]
}

type LineMetrics = {
  line: 14 | 17 | 19
  oee: number
  h_productive: number
  h_changeover: number
  h_cleaning: number
  h_maintenance: number
  h_idle: number
  coverage: number
}

type DroppedSku = {
  sku: string
  units_demanded: number
  units_dropped: number
  margin_lost: number
  reason: string
}
```

### DeltaMetrics

All deltas are signed in favor of LineWise.

```ts
type DeltaMetrics = {
  oee_pp: number
  h_changes_saved: number
  h_productive_gained: number
  coverage_delta: number
}
```

## 3. Optimize A Plan

```http
POST /linewise/optimize
```

Used by the Plan page after manual entry or CSV upload.

### Request

```ts
type PlanOptimizeRequest = {
  products: {
    sku_id: string
    quantity_units: number
  }[]
}
```

### Response

```ts
type PlanOptimizeResponse = {
  nodes: PlanGraphNode[]
  edges: PlanGraphEdge[]
  makespan_h: number
  h_saved: number
  coverage_pct: number
  dropped_skus: string[]
}

type PlanGraphNode = {
  id: string
  label: string
  line_id: 14 | 17 | 19
  family: string
  volume_hl: number
}

type PlanGraphEdge = {
  id: string
  source: string
  target: string
  hours: number
  path: 'opt' | 'baseline'
}
```

The graph can include both baseline and optimized edges. The frontend renders:

- `path: "baseline"` as the real/JDA order.
- `path: "opt"` as the LineWise proposal.

## 4. Replan What-if Scenario

```http
POST /linewise/replan
```

Used by the What-if page after a perturbation.

### Request

```ts
type ReplanRequest = {
  scenario_id: string
  introduced_at?: string
  urgent_sku?: string
  urgent_units?: number
  breakdown_line?: 14 | 17 | 19
  breakdown_day?: string
  breakdown_hours?: number
}
```

`introduced_at` is the ISO timestamp when the planner learns about the perturbation.
The backend should replan from this point onward.

Current frontend scenario IDs:

```text
urgent-demand
l14-breakdown
```

### Response

```ts
type ReplanScenario = {
  id: string
  label: string
  description: string
  recommendation: {
    assignedLine?: 14 | 17 | 19
    headline: string
    why: string
    constraints: string[]
  }
  sequence: Sequence
  report: SimulationReport
  base: SimulationReport
}
```

## 5. Chat

```http
POST /linewise/chat
```

Used by all LineWise pages. The backend should ground responses on the `solution_id` explanation pack.

### Request

```ts
type ChatRequest = {
  solution_id: string
  scope: ChatScope
  history: ChatMessage[]
  user_message: string
}

type ChatScope = {
  view?: 'plan' | 'compare' | 'what-if' | 'insights'
  line_id?: 14 | 17 | 19
  slot_id?: string
  transition_id?: string
  sku_id?: string
  dropped_sku_id?: string
}

type ChatMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
}
```

### Response

```ts
type ChatResponse = {
  assistant_message: string
  referenced?: GroundingReference[]
}

type GroundingReference = {
  kind: 'solution' | 'line' | 'theme' | 'slot' | 'transition' | 'counterfactual' | 'dropped_sku'
  ref_id: string
}
```

## Minimum Backend Milestone

For the frontend to stop showing mock graphics, implement these first:

1. `GET /linewise/weeks`
2. `GET /linewise/compare?week_id=...`

Then add:

3. `POST /linewise/optimize`
4. `POST /linewise/replan`
5. `POST /linewise/chat`

The Compare bundle is the most important integration point because it feeds the Gantt, KPI summary, changeover table, and chat grounding.
