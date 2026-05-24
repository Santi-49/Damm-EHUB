'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { AlertTriangle, Clock, Euro, Factory, Route, ShieldCheck } from 'lucide-react'
import {
  chatSeedCompare,
  getCompareBundle,
  listWeeks,
  MOCK_WEEK_OPTIONS,
  type ApiResult,
  type CompareBundle,
  type DataSource,
  type WeekOption,
} from '@/lib/linewise-api'
import { ChatPanel } from './chat-panel'
import { GANTT_DAY_OPTIONS, GanttChart, type GanttViewport } from './gantt-chart'
import { LineScorecard } from './line-scorecard'
import { TopTransitions } from './top-transitions'
import type { DeltaMetrics, Sequence, SimulationReport } from '@/lib/types/linewise'

export function CompareWorkspace() {
  const searchParams = useSearchParams()
  const initialWeekId = searchParams.get('week_id') ?? MOCK_WEEK_OPTIONS[0].id
  const [weeksResult, setWeeksResult] = useState<ApiResult<WeekOption[]>>({
    data: MOCK_WEEK_OPTIONS,
    source: 'mock',
  })
  const [selectedWeekId, setSelectedWeekId] = useState(initialWeekId)
  const [compareResult, setCompareResult] = useState<ApiResult<CompareBundle> | null>(null)
  const [ganttViewport, setGanttViewport] = useState<GanttViewport>('week')
  const [loading, setLoading] = useState(false)
  const weeks = weeksResult.data
  const selectedWeek = compareResult?.data.week ?? weeks.find(w => w.id === selectedWeekId) ?? MOCK_WEEK_OPTIONS[0]
  const dropdownWeeks = weeks.some(w => w.id === selectedWeek.id) ? weeks : [selectedWeek, ...weeks]

  useEffect(() => {
    let active = true
    listWeeks().then(result => {
      if (!active) return
      setWeeksResult(result)
    })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    getCompareBundle(selectedWeekId).then(result => {
      if (!active) return
      setCompareResult(result)
      setLoading(false)
    })
    return () => { active = false }
  }, [selectedWeekId])

  const bundle = compareResult?.data

  return (
    <div className="flex flex-col gap-6">
      <CompareHeader
        weeks={dropdownWeeks}
        selectedWeek={selectedWeek}
        apiSource={compareResult?.source ?? weeksResult.source}
        loading={loading}
        onWeekChange={setSelectedWeekId}
      />

      {selectedWeek.source === 'historical' && compareResult?.source === 'mock' && (
        <HistoricalWeekNotice week={selectedWeek} />
      )}

      {bundle && (
        <>
          <ImpactSummary
            opt={bundle.opt_simulation}
            real={bundle.real_simulation}
            delta={bundle.delta}
            realSequence={bundle.real_sequence}
            optSequence={bundle.opt_sequence}
          />

          <div className="flex flex-col gap-3">
            <GanttZoomControl value={ganttViewport} onChange={setGanttViewport} />
            <GanttChart sequence={bundle.real_sequence} title="S_real — what actually happened" viewport={ganttViewport} />
            <GanttChart sequence={bundle.opt_sequence} title="S_opt — LineWise proposal from backend" viewport={ganttViewport} />
          </div>

          <LineScorecard real={bundle.real_simulation} opt={bundle.opt_simulation} />

          <TopTransitions real={bundle.real_sequence} opt={bundle.opt_sequence} />

          <ChatPanel
            solutionId={bundle.solution_id}
            scope={{ view: 'compare' }}
            seedMessages={chatSeedCompare}
          />
        </>
      )}
    </div>
  )
}

function GanttZoomControl({
  value,
  onChange,
}: {
  value: GanttViewport
  onChange: (value: GanttViewport) => void
}) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium">Gantt zoom</p>
        <p className="text-xs text-muted-foreground">
          Switch to a day view to inspect each line hour by hour.
        </p>
      </div>
      <Select value={value} onValueChange={value => onChange(value as GanttViewport)}>
        <SelectTrigger className="w-full sm:w-44">
          <SelectValue placeholder="Select zoom" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="week">Full week</SelectItem>
          {GANTT_DAY_OPTIONS.map(day => (
            <SelectItem key={day.value} value={day.value}>
              {day.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function CompareHeader({
  weeks,
  selectedWeek,
  apiSource,
  loading,
  onWeekChange,
}: {
  weeks: WeekOption[]
  selectedWeek: WeekOption
  apiSource: DataSource
  loading: boolean
  onWeekChange: (weekId: string) => void
}) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="max-w-3xl">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-3xl font-bold tracking-tight">Compare</h1>
          <Badge variant="secondary">One week audit</Badge>
        </div>
        <p className="text-muted-foreground mt-1">
          Pick a production week, then compare Damm&apos;s real execution against the LineWise sequence for the same demand window.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Backend endpoint: <code className="font-mono">GET /api/v1/linewise/compare</code>. Falls back to demo fixtures until the engine is ready.
        </p>
      </div>

      <div className="w-full lg:w-96 rounded-xl border bg-card p-4">
        <label htmlFor="compare-week" className="text-sm font-medium">
          Week to audit
        </label>
        <Select value={selectedWeek.id} onValueChange={onWeekChange}>
          <SelectTrigger id="compare-week" className="mt-2 w-full">
            <SelectValue placeholder="Select a week" />
          </SelectTrigger>
          <SelectContent>
            {weeks.map(week => (
              <SelectItem key={week.id} value={week.id}>
                {week.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="mt-3 rounded-lg bg-muted/40 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {selectedWeek.range}
            </p>
            <Badge variant={apiSource === 'backend' ? 'default' : 'outline'}>
              {loading ? 'Loading' : apiSource === 'backend' ? 'Backend result' : 'Mock fallback'}
            </Badge>
          </div>
          <p className="mt-2 text-sm leading-relaxed">{selectedWeek.reason}</p>
        </div>
      </div>
    </div>
  )
}

function HistoricalWeekNotice({ week }: { week: WeekOption }) {
  return (
    <Card className="border-amber-200 bg-amber-50/70">
      <CardContent className="flex flex-col gap-3 pt-4 sm:flex-row sm:items-start">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div>
          <p className="font-medium text-amber-950">
            Historical week selected; showing the demo comparison until backend optimisation is wired.
          </p>
          <p className="mt-1 text-sm text-amber-900/80">
            `data/clean` currently has `wo_master.csv` and `skus.csv`, enough to suggest weeks like {week.id}, but not enough for the browser to calculate `S_opt`. The backend should receive the week demand and return the LineWise distribution.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

function ImpactSummary({
  opt,
  real,
  delta,
  realSequence,
  optSequence,
}: {
  opt: SimulationReport
  real: SimulationReport
  delta: DeltaMetrics
  realSequence: Sequence
  optSequence: Sequence
}) {
  const marginRecovered = real.dropped_skus.reduce((sum, sku) => sum + sku.margin_lost, 0)
  const unitsRecovered = real.dropped_skus.reduce((sum, sku) => sum + sku.units_dropped, 0)
  const avoidedOverrunH = computeAvoidedChangeoverHours(realSequence, optSequence)
  const oeePp = delta.oee_pp * 100

  const tiles = [
    {
      icon: Factory,
      heading: `+${delta.h_productive_gained.toFixed(1)} h`,
      label: 'capacity recovered',
      sub: `${real.h_productive} h real → ${opt.h_productive} h LineWise`,
      tone: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    },
    {
      icon: Route,
      heading: `−${delta.h_changes_saved.toFixed(1)} h`,
      label: 'changeover waste avoided',
      sub: `${avoidedOverrunH.toFixed(1)} h explained by matched transitions`,
      tone: 'text-blue-700 bg-blue-50 border-blue-200',
    },
    {
      icon: ShieldCheck,
      heading: `+${(delta.coverage_delta * 100).toFixed(0)} pp`,
      label: 'demand protected',
      sub: unitsRecovered > 0 ? `${unitsRecovered.toLocaleString()} units recovered` : 'No demand left behind',
      tone: 'text-primary bg-primary/5 border-primary/20',
    },
    {
      icon: Euro,
      heading: `€${marginRecovered.toLocaleString()}`,
      label: 'margin at risk — recovered',
      sub: `${real.dropped_skus.length} SKU${real.dropped_skus.length === 1 ? '' : 's'} left unproduced in S_real`,
      tone: 'text-amber-700 bg-amber-50 border-amber-200',
    },
  ]

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-muted/20">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle className="text-xl">LineWise wins this week by protecting capacity, not by predicting OEE</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Same demand window, same operational constraints. The proposal shortens expensive transitions and converts that time back into production.
            </p>
          </div>
          <div className="rounded-lg border bg-background px-3 py-2 text-sm">
            <div className="flex items-center gap-2 font-medium">
              <Clock className="h-4 w-4 text-primary" />
              OEE uplift: <span className="tabular-nums text-emerald-700">+{oeePp.toFixed(1)} pp</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Supporting KPI: {(real.oee_global * 100).toFixed(1)}% → {(opt.oee_global * 100).toFixed(1)}%
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {tiles.map(tile => (
            <div key={tile.label} className={`rounded-xl border p-4 ${tile.tone}`}>
              <tile.icon className="mb-3 h-5 w-5" />
              <p className="text-2xl font-bold tabular-nums leading-none">{tile.heading}</p>
              <p className="mt-1 text-sm font-semibold">{tile.label}</p>
              <p className="mt-1 text-xs opacity-80">{tile.sub}</p>
            </div>
          ))}
        </div>

        {real.dropped_skus.length > 0 && (
          <div className="border-t pt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              S_real left unproduced — LineWise covers all demand
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {real.dropped_skus.map(d => (
                <div
                  key={d.sku}
                  className="flex items-start justify-between gap-3 rounded-lg border border-red-200 bg-red-50/50 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-mono font-semibold text-red-900">{d.sku}</p>
                    <p className="text-[10px] text-red-700 mt-0.5 leading-relaxed">{d.reason}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-bold tabular-nums text-red-800">€{d.margin_lost.toLocaleString()}</p>
                    <p className="text-[10px] text-red-600">{d.units_dropped.toLocaleString()} units</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function computeAvoidedChangeoverHours(real: Sequence, opt: Sequence) {
  const optChangeovers = opt.slots.filter(slot => slot.kind === 'changeover')

  return real.slots
    .filter(slot => slot.kind === 'changeover' && slot.changeover_h != null)
    .reduce((total, realSlot) => {
      const match = optChangeovers.find(
        optSlot => optSlot.line === realSlot.line && optSlot.sku === realSlot.sku,
      )
      if (match?.changeover_h == null || realSlot.changeover_h == null) return total
      return total + Math.max(0, realSlot.changeover_h - match.changeover_h)
    }, 0)
}
