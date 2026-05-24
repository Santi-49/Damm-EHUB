import {
  PLACEHOLDER_SOLUTION_ID,
  chatSeedCompare,
  computeDelta,
  sequenceOpt,
  sequenceReal,
  simulationOpt,
  simulationReal,
} from '@/lib/fixtures'
import { pickFallback } from '@/lib/fixtures/chat-messages'
import { impactAtlas2025 } from '@/lib/fixtures/impact-atlas'
import { replanScenarios, type ReplanScenario } from '@/lib/fixtures/replan-scenarios'
import type { ChatRequest, ChatResponse } from '@/lib/types/chat'
import type { ImpactAtlas } from '@/lib/types/insights'
import type { Line, Sequence, SimulationReport, Slot } from '@/lib/types/linewise'
import type {
  PlanGraphEdge,
  PlanGraphNode,
  PlanOptimizeRequest,
  PlanOptimizeResponse,
  PlanProduct,
} from '@/lib/types/plan-api'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export type DataSource = 'backend' | 'mock'

export interface ApiResult<T> {
  data: T
  source: DataSource
}

export interface WeekOption {
  id: string
  label: string
  range: string
  source: 'demo' | 'historical'
  reason: string
  production_rows?: number
  sku_count?: number
  units?: number
  avg_oee?: number
  downtime_h?: number
}

export interface CompareBundle {
  week: WeekOption
  solution_id: string
  real_sequence: Sequence
  opt_sequence: Sequence
  real_simulation: SimulationReport
  opt_simulation: SimulationReport
  delta: ReturnType<typeof computeDelta>
}

export interface ReplanRequest {
  scenario_id: string
  introduced_at?: string
  required_by?: string
  urgent_sku?: string
  urgent_units?: number
  breakdown_line?: Line
  breakdown_day?: string
  breakdown_hours?: number
}

export const MOCK_WEEK_OPTIONS: WeekOption[] = [
  {
    id: '2026-W20-demo',
    label: '2026-W20 · demo week',
    range: '18–24 May 2026',
    source: 'demo',
    reason: 'Best showcase: Damm plan, real execution, and LineWise recommendation are already mocked end-to-end.',
  },
  {
    id: '2025-W30',
    label: '2025-W30 · high SKU variety',
    range: '21–27 Jul 2025',
    source: 'historical',
    reason: '50 production WOs across 46 SKUs. Good stress test for sequencing complexity.',
    production_rows: 50,
    sku_count: 46,
    units: 15855686,
    avg_oee: 0.521,
    downtime_h: 207.4,
  },
  {
    id: '2025-W25',
    label: '2025-W25 · heavy volume',
    range: '16–22 Jun 2025',
    source: 'historical',
    reason: '48 production WOs and 18.6M units. Good week to test capacity recovery.',
    production_rows: 48,
    sku_count: 44,
    units: 18607194,
    avg_oee: 0.574,
    downtime_h: 185.2,
  },
  {
    id: '2025-W14',
    label: '2025-W14 · many changeovers',
    range: '31 Mar–6 Apr 2025',
    source: 'historical',
    reason: '48 production WOs and many changeover flags. Good week for explaining transition waste.',
    production_rows: 48,
    sku_count: 46,
    units: 13022100,
    avg_oee: 0.463,
    downtime_h: 180.9,
  },
]

async function linewiseRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  }

  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    throw new Error(`LineWise API ${endpoint} returned ${response.status}`)
  }

  if (response.status === 204) return null as T
  return response.json()
}

export async function listWeeks(): Promise<ApiResult<WeekOption[]>> {
  try {
    const weeks = await linewiseRequest<WeekOption[]>('/linewise/weeks')
    return { data: weeks, source: 'backend' }
  } catch {
    return { data: MOCK_WEEK_OPTIONS, source: 'mock' }
  }
}

export async function getImpactAtlas(year = 2025): Promise<ApiResult<ImpactAtlas>> {
  try {
    const atlas = await linewiseRequest<ImpactAtlas>(`/linewise/impact-atlas?year=${year}`)
    return { data: atlas, source: 'backend' }
  } catch {
    return { data: impactAtlas2025, source: 'mock' }
  }
}

export async function getCompareBundle(weekId: string): Promise<ApiResult<CompareBundle>> {
  try {
    const bundle = await linewiseRequest<CompareBundle>(
      `/linewise/compare?week_id=${encodeURIComponent(weekId)}`,
    )
    return { data: bundle, source: 'backend' }
  } catch {
    return { data: buildMockCompareBundle(weekId), source: 'mock' }
  }
}

export async function optimizePlan(request: PlanOptimizeRequest): Promise<ApiResult<PlanOptimizeResponse>> {
  try {
    const response = await linewiseRequest<PlanOptimizeResponse>('/linewise/optimize', {
      method: 'POST',
      body: JSON.stringify(request),
    })
    return { data: response, source: 'backend' }
  } catch {
    await delay(1200)
    return { data: buildMockPlanResponse(request.products), source: 'mock' }
  }
}

export async function runReplan(request: ReplanRequest): Promise<ApiResult<ReplanScenario>> {
  try {
    const response = await linewiseRequest<ReplanScenario>('/linewise/replan', {
      method: 'POST',
      body: JSON.stringify(request),
    })
    return { data: response, source: 'backend' }
  } catch {
    await delay(1200)
    return {
      data: replanScenarios.find(s => s.id === request.scenario_id) ?? replanScenarios[0],
      source: 'mock',
    }
  }
}

export async function sendChatMessage(request: ChatRequest): Promise<ApiResult<ChatResponse>> {
  try {
    const response = await linewiseRequest<ChatResponse>('/linewise/chat', {
      method: 'POST',
      body: JSON.stringify(request),
    })
    return { data: response, source: 'backend' }
  } catch {
    await delay(600)
    return {
      data: {
        assistant_message: pickFallback(request.scope.view),
        referenced: [],
      },
      source: 'mock',
    }
  }
}

function buildMockCompareBundle(weekId: string): CompareBundle {
  const week = MOCK_WEEK_OPTIONS.find(w => w.id === weekId)
    ?? buildWeekOptionFromAtlas(weekId)
    ?? MOCK_WEEK_OPTIONS[0]

  return {
    week,
    solution_id: PLACEHOLDER_SOLUTION_ID,
    real_sequence: sequenceReal,
    opt_sequence: sequenceOpt,
    real_simulation: simulationReal,
    opt_simulation: simulationOpt,
    delta: computeDelta(),
  }
}

// Synthesise a WeekOption when the user lands on Compare from the Insights
// heatmap with a week we haven't manually scripted. Keeps the header honest
// (correct week id + date range) even though the sequences below remain the
// demo fixtures until the backend ships.
function buildWeekOptionFromAtlas(weekId: string): WeekOption | null {
  const entry = impactAtlas2025.weeks.find(w => w.week_id === weekId)
  if (!entry) return null
  const start = new Date(entry.week_start + 'T00:00:00Z')
  const end = new Date(entry.week_end + 'T00:00:00Z')
  const fmt = (d: Date) => d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
  return {
    id: entry.week_id,
    label: `${entry.week_id} · from Impact Atlas`,
    range: `${fmt(start)} – ${fmt(end)} ${start.getUTCFullYear()}`,
    source: 'historical',
    reason: `Selected from the 2025 leaderboard — €${entry.margin_recovered.toLocaleString()} recoverable, ${entry.hours_recovered.toFixed(1)}h changeover saved.`,
  }
}

function assignLine(sku: string, idx: number): Line {
  const upper = sku.toUpperCase()
  if (upper.includes('2/5') || upper.includes('44CL') || upper.includes('44 CL')) return 19
  if (upper.includes('1/2') || upper.includes('50CL') || upper.includes('50 CL')) return idx % 2 === 0 ? 14 : 19

  const options: Line[] = [14, 17, 19]
  return options[idx % 3]
}

function inferFamily(sku: string): string {
  const upper = sku.toUpperCase()
  if (upper.match(/^(ESTB|ESTRELLA|ED)/)) return 'DAMM'
  if (upper.match(/^(FREQ|FREE|FD)/)) return 'FREQ'
  if (upper.match(/^(LEMO|DAMM\.LEMON|DL)/)) return 'LEMO'
  if (upper.match(/^(DAURA|XI)/)) return 'DAURA'
  if (upper.match(/^(VOLL|TU)/)) return 'VOLL'
  if (upper.match(/^(KELER|KE|RDSQ)/)) return 'RDSQ'
  return 'DAMM'
}

function buildMockPlanResponse(products: PlanProduct[]): PlanOptimizeResponse {
  const lined = products.map((product, index) => ({
    ...product,
    line_id: assignLine(product.sku_id, index),
    family: inferFamily(product.sku_id),
    volume_hl: Math.max(10, Math.round(product.quantity_units / 100)),
  }))

  const byLine: Record<number, typeof lined> = { 14: [], 17: [], 19: [] }
  lined.forEach(product => byLine[product.line_id].push(product))

  const nodes: PlanGraphNode[] = lined.map(product => ({
    id: product.sku_id,
    label: product.sku_id.split('-').slice(0, 2).join(' '),
    line_id: product.line_id,
    family: product.family,
    volume_hl: product.volume_hl,
  }))

  const edges: PlanGraphEdge[] = []
  let edgeIndex = 0

  Object.values(byLine).forEach(items => {
    for (let index = 0; index < items.length - 1; index++) {
      const optH = +(0.3 + Math.random() * 0.5).toFixed(1)
      const baseH = +(optH + 0.7 + Math.random() * 1.4).toFixed(1)
      edges.push({ id: `o${edgeIndex}`, source: items[index].sku_id, target: items[index + 1].sku_id, hours: optH, path: 'opt' })
      edges.push({ id: `b${edgeIndex}`, source: items[index].sku_id, target: items[index + 1].sku_id, hours: baseH, path: 'baseline' })
      edgeIndex++
    }
  })

  const optTotal = edges.filter(edge => edge.path === 'opt').reduce((sum, edge) => sum + edge.hours, 0)
  const baseTotal = edges.filter(edge => edge.path === 'baseline').reduce((sum, edge) => sum + edge.hours, 0)

  const sequence = buildPlanSequence(byLine, edges)

  return {
    nodes,
    edges,
    makespan_h: +(products.length * 3.8 + optTotal).toFixed(1),
    h_saved: +(baseTotal - optTotal).toFixed(1),
    coverage_pct: 1.0,
    dropped_skus: [],
    sequence,
  }
}

// Synthesise a per-line Gantt schedule from the per-line product grouping.
// Anchored at Mon 18 May 2026 06:00 so the labels match the existing Gantt
// day ruler ('Mon 18'…'Sat 23'). Replace with the backend sequence once the
// optimiser ships.
const PLAN_WEEK_START = '2026-05-18T06:00:00'
const PLAN_WEEK_END = '2026-05-24T22:00:00'
const HOUR_MS = 3_600_000

function buildPlanSequence(
  byLine: Record<number, Array<{ sku_id: string; quantity_units: number; line_id: Line; family: string }>>,
  edges: PlanGraphEdge[],
): Sequence {
  const optEdgeHours = new Map(
    edges.filter(e => e.path === 'opt').map(e => [`${e.source}→${e.target}`, e.hours]),
  )
  const startMs = new Date(PLAN_WEEK_START).getTime()
  const slots: Slot[] = []

  ;([14, 17, 19] as Line[]).forEach(line => {
    const items = byLine[line] ?? []
    if (items.length === 0) return
    let cursorMs = startMs

    items.forEach((product, i) => {
      const prodHours = Math.max(2, Math.min(18, product.quantity_units / 4000))
      const prodEnd = cursorMs + prodHours * HOUR_MS
      slots.push({
        id: `plan-l${line}-p${i}`,
        line,
        start: new Date(cursorMs).toISOString(),
        end: new Date(prodEnd).toISOString(),
        kind: 'production',
        sku: product.sku_id,
        label: product.sku_id,
        units: product.quantity_units,
        oee_expected: +(0.78 + (i % 5) * 0.012).toFixed(3),
      })
      cursorMs = prodEnd

      if (i < items.length - 1) {
        const next = items[i + 1]
        const changeoverH = optEdgeHours.get(`${product.sku_id}→${next.sku_id}`) ?? 0.5
        const coEnd = cursorMs + changeoverH * HOUR_MS
        slots.push({
          id: `plan-l${line}-c${i}`,
          line,
          start: new Date(cursorMs).toISOString(),
          end: new Date(coEnd).toISOString(),
          kind: 'changeover',
          sku: product.sku_id,
          label: `→ ${next.family}`,
          changeover_h: changeoverH,
          changeover_source: 'ml',
        })
        cursorMs = coEnd
      }
    })
  })

  return {
    id: 'plan-opt',
    week_id: '2026-W20',
    week_start: PLAN_WEEK_START,
    week_end: PLAN_WEEK_END,
    source: 'opt',
    slots,
  }
}

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export { chatSeedCompare }
