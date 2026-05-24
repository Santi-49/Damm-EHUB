'use client'

import { useState } from 'react'
import { replanScenarios, type ReplanScenario } from '@/lib/fixtures/replan-scenarios'
import { GanttChart } from './gantt-chart'
import { RecommendationCard } from './recommendation-card'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Zap, WifiOff, ChevronRight, RotateCcw, Loader2 } from 'lucide-react'
import { runReplan, type DataSource } from '@/lib/linewise-api'

const SCENARIO_ICONS = {
  'urgent-demand': Zap,
  'l14-breakdown': WifiOff,
} as const

type ScenarioId = keyof typeof SCENARIO_ICONS

const SKU_OPTIONS = [
  { sku: 'ED13LP12', label: 'Estrella Damm 1/3 Pack 12', format: '1/3', compatibleLines: [14, 17, 19], l19Speed: 80667 },
  { sku: 'ED13LTW',  label: 'Estrella Damm 1/3 lata',    format: '1/3', compatibleLines: [14, 17, 19], l19Speed: 78584 },
  { sku: 'TU13LTN',  label: 'Turia 1/3 lata',            format: '1/3', compatibleLines: [14, 17, 19], l19Speed: 74005 },
]

const DAY_OPTIONS = [
  { value: '2024-12-30', label: 'Mon 30 Dec' },
  { value: '2024-12-31', label: 'Tue 31 Dec' },
  { value: '2025-01-01', label: 'Wed 1 Jan' },
  { value: '2025-01-02', label: 'Thu 2 Jan' },
  { value: '2025-01-03', label: 'Fri 3 Jan' },
]

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) => ({
  value: hour,
  label: `${String(hour).padStart(2, '0')}:00`,
}))

export function WhatIfForm() {
  const [scenarioId, setScenarioId] = useState<ScenarioId>('urgent-demand')
  const [introductionDay, setIntroductionDay] = useState('2024-12-31')
  const [introductionHour, setIntroductionHour] = useState(8)
  const [requiredDay, setRequiredDay] = useState('2025-01-03')
  const [requiredHour, setRequiredHour] = useState(18)
  const [urgentSku,  setUrgentSku]  = useState('ED13LP12')
  const [urgentUnits, setUrgentUnits] = useState(8000)
  const [breakdownLine, setBreakdownLine] = useState<14 | 17 | 19>(14)
  const [breakdownDay,  setBreakdownDay]  = useState('2024-12-31')
  const [breakdownH,    setBreakdownH]    = useState(8)
  const [loading, setLoading]             = useState(false)
  const [result, setResult]               = useState<ReplanScenario | null>(null)
  const [resultSource, setResultSource]   = useState<DataSource | null>(null)

  const selectedSku = SKU_OPTIONS.find(s => s.sku === urgentSku)!
  const introducedAt = `${introductionDay}T${String(introductionHour).padStart(2, '0')}:00:00`
  const requiredBy = `${requiredDay}T${String(requiredHour).padStart(2, '0')}:00:00`

  async function handleReplan() {
    setLoading(true)
    setResult(null)
    setResultSource(null)

    const response = await runReplan({
      scenario_id: scenarioId,
      introduced_at: introducedAt,
      required_by: scenarioId === 'urgent-demand' ? requiredBy : undefined,
      urgent_sku: urgentSku,
      urgent_units: urgentUnits,
      breakdown_line: breakdownLine,
      breakdown_day: breakdownDay,
      breakdown_hours: breakdownH,
    })

    setResult(response.data)
    setResultSource(response.source)
    setLoading(false)
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── Scenario selector ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {replanScenarios.map(s => {
          const Icon = SCENARIO_ICONS[s.id as ScenarioId]
          const active = scenarioId === s.id
          return (
            <button
              key={s.id}
              onClick={() => { setScenarioId(s.id as ScenarioId); setResult(null) }}
              className={[
                'rounded-xl border-2 p-4 text-left transition-all',
                active
                  ? 'border-primary bg-primary/5'
                  : 'border-border bg-card hover:border-primary/40 hover:bg-muted/30',
              ].join(' ')}
            >
              <div className="flex items-center gap-2 mb-2">
                <Icon className={`h-4 w-4 ${active ? 'text-primary' : 'text-muted-foreground'}`} />
                <span className={`text-sm font-semibold ${active ? 'text-primary' : ''}`}>{s.label}</span>
              </div>
              <p className="text-xs text-muted-foreground leading-snug">{s.description}</p>
            </button>
          )
        })}
      </div>

      {/* ── Parameters ── */}
      <Card>
        <CardContent className="pt-5 pb-5">
          <div className="space-y-4">
            <p className="text-sm font-medium">When does the new information arrive?</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-muted-foreground mb-1.5">Weekday</label>
                <select
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={introductionDay}
                  onChange={e => setIntroductionDay(e.target.value)}
                >
                  {DAY_OPTIONS.map(d => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1.5">Hour</label>
                <select
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={introductionHour}
                  onChange={e => setIntroductionHour(Number(e.target.value))}
                >
                  {HOUR_OPTIONS.map(h => (
                    <option key={h.value} value={h.value}>{h.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              The planner receives this what-if at {introducedAt.replace('T', ' ')} and only replans from that point onward.
            </p>
          </div>

          {scenarioId === 'urgent-demand' && (
            <div className="space-y-4 mt-5 pt-4 border-t">
              <p className="text-sm font-medium">Perturbation parameters</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-muted-foreground mb-1.5">SKU</label>
                  <select
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    value={urgentSku}
                    onChange={e => setUrgentSku(e.target.value)}
                  >
                    {SKU_OPTIONS.map(o => (
                      <option key={o.sku} value={o.sku}>{o.label}</option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground mt-1.5">
                    Format {selectedSku.format} · Compatible lines:{' '}
                    {selectedSku.compatibleLines.map(l => `L${l}`).join(', ')}
                  </p>
                </div>
                <div>
                  <label className="block text-xs text-muted-foreground mb-1.5">
                    Additional units demanded
                  </label>
                  <input
                    type="number"
                    min={1000}
                    max={50000}
                    step={1000}
                    value={urgentUnits}
                    onChange={e => setUrgentUnits(Number(e.target.value))}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary tabular-nums"
                  />
                  <p className="text-xs text-muted-foreground mt-1.5">
                    ≈ {(urgentUnits / selectedSku.l19Speed).toFixed(1)} h extra production on L19
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-muted-foreground mb-1.5">Required by day</label>
                  <select
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    value={requiredDay}
                    onChange={e => setRequiredDay(e.target.value)}
                  >
                    {DAY_OPTIONS.map(d => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-muted-foreground mb-1.5">Required by hour</label>
                  <select
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    value={requiredHour}
                    onChange={e => setRequiredHour(Number(e.target.value))}
                  >
                    {HOUR_OPTIONS.map(h => (
                      <option key={h.value} value={h.value}>{h.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}

          {scenarioId === 'l14-breakdown' && (
            <div className="space-y-4 mt-5 pt-4 border-t">
              <p className="text-sm font-medium">Breakdown parameters</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs text-muted-foreground mb-1.5">Affected line</label>
                  <select
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    value={breakdownLine}
                    onChange={e => setBreakdownLine(Number(e.target.value) as 14 | 17 | 19)}
                  >
                    <option value={14}>L14</option>
                    <option value={17}>L17</option>
                    <option value={19}>L19</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-muted-foreground mb-1.5">Day</label>
                  <select
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    value={breakdownDay}
                    onChange={e => setBreakdownDay(e.target.value)}
                  >
                    {DAY_OPTIONS.map(d => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-muted-foreground mb-1.5">Duration (hours)</label>
                  <input
                    type="number"
                    min={1}
                    max={24}
                    value={breakdownH}
                    onChange={e => setBreakdownH(Number(e.target.value))}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary tabular-nums"
                  />
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center gap-3 mt-5 pt-4 border-t">
            <Button onClick={handleReplan} disabled={loading} className="gap-2">
              {loading
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Re-planning…</>
                : <><ChevronRight className="h-4 w-4" /> Run re-plan</>
              }
            </Button>
            {result && (
              <Button variant="ghost" size="sm" onClick={() => setResult(null)} className="gap-1.5 text-muted-foreground">
                <RotateCcw className="h-3.5 w-3.5" /> Reset
              </Button>
            )}
            <span className="text-xs text-muted-foreground ml-auto">Target latency &lt; 5 s</span>
          </div>
        </CardContent>
      </Card>

      {/* ── Result ── */}
      {result && (
        <div className="flex flex-col gap-5 animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">
              Re-plan complete
            </Badge>
            {resultSource && (
              <Badge variant={resultSource === 'backend' ? 'default' : 'outline'} className="text-xs">
                {resultSource === 'backend' ? 'Backend result' : 'Mock fallback'}
              </Badge>
            )}
            <span className="text-xs text-muted-foreground">Comparing against S_opt baseline</span>
          </div>

          <RecommendationCard scenario={result} />

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <GanttChart sequence={result.base_sequence} title="Original S_opt planning — full week" />
            <GanttChart sequence={result.sequence} title="What-if replan — full week" />
          </div>
        </div>
      )}
    </div>
  )
}
