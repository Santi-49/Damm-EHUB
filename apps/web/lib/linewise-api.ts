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
import { replanScenarios, type ReplanScenario } from '@/lib/fixtures/replan-scenarios'
import type { ChatRequest, ChatResponse } from '@/lib/types/chat'
import type { Line, Sequence, SimulationReport } from '@/lib/types/linewise'
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
  productionRows?: number
  skuCount?: number
  units?: number
  avgOee?: number
  downtimeH?: number
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
    productionRows: 50,
    skuCount: 46,
    units: 15855686,
    avgOee: 0.521,
    downtimeH: 207.4,
  },
  {
    id: '2025-W25',
    label: '2025-W25 · heavy volume',
    range: '16–22 Jun 2025',
    source: 'historical',
    reason: '48 production WOs and 18.6M units. Good week to test capacity recovery.',
    productionRows: 48,
    skuCount: 44,
    units: 18607194,
    avgOee: 0.574,
    downtimeH: 185.2,
  },
  {
    id: '2025-W14',
    label: '2025-W14 · many changeovers',
    range: '31 Mar–6 Apr 2025',
    source: 'historical',
    reason: '48 production WOs and many changeover flags. Good week for explaining transition waste.',
    productionRows: 48,
    skuCount: 46,
    units: 13022100,
    avgOee: 0.463,
    downtimeH: 180.9,
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
  const week = MOCK_WEEK_OPTIONS.find(w => w.id === weekId) ?? MOCK_WEEK_OPTIONS[0]

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

  return {
    nodes,
    edges,
    makespan_h: +(products.length * 3.8 + optTotal).toFixed(1),
    h_saved: +(baseTotal - optTotal).toFixed(1),
    coverage_pct: 1.0,
    dropped_skus: [],
  }
}

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export { chatSeedCompare }
