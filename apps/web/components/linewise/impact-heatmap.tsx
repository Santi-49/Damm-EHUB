'use client'

import { useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { ImpactAtlas, WeekImpact } from '@/lib/types/insights'

interface ImpactHeatmapProps {
  atlas: ImpactAtlas
}

const QUARTERS: Array<{ label: string; weeks: [number, number] }> = [
  { label: 'Q1', weeks: [1, 13] },
  { label: 'Q2', weeks: [14, 26] },
  { label: 'Q3', weeks: [27, 39] },
  { label: 'Q4', weeks: [40, 52] },
]

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Map € recovered to a 0-4 intensity bin. Thresholds picked from the mock data
// so most weeks land in 1-2 and the worst weeks pop in 4.
function intensity(margin: number): 0 | 1 | 2 | 3 | 4 {
  if (margin <= 0) return 0
  if (margin < 12_000) return 1
  if (margin < 25_000) return 2
  if (margin < 45_000) return 3
  return 4
}

const BIN_CLASSES: Record<number, string> = {
  0: 'bg-muted/30 border-muted',
  1: 'bg-emerald-100 border-emerald-200 hover:border-emerald-400',
  2: 'bg-emerald-200 border-emerald-300 hover:border-emerald-500',
  3: 'bg-emerald-400 border-emerald-500 hover:border-emerald-700',
  4: 'bg-emerald-600 border-emerald-700 hover:border-emerald-900',
}

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

export function ImpactHeatmap({ atlas }: ImpactHeatmapProps) {
  const router = useRouter()

  const handleClick = (week: WeekImpact) => {
    if (!week.has_production) return
    router.push(`/compare?week_id=${week.week_id}`)
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b py-3">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <CardTitle className="text-base">2025 calendar — recovery potential per week</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">
              Deeper green = more margin LineWise would have recovered. Click any week to open the side-by-side comparison.
            </p>
          </div>
          <Legend />
        </div>
      </CardHeader>
      <CardContent className="pt-5 pb-5">
        <TooltipProvider delayDuration={120}>
          <div className="flex flex-col gap-2.5">
            {QUARTERS.map(({ label, weeks }) => {
              const [from, to] = weeks
              const quarterWeeks = atlas.weeks.slice(from - 1, to)
              const monthsInQuarter = MONTH_LABELS.slice((from - 1) / 13 * 3, (from - 1) / 13 * 3 + 3)
              return (
                <div key={label} className="flex items-center gap-3">
                  <div className="flex flex-col w-9 shrink-0">
                    <span className="text-xs font-semibold text-foreground">{label}</span>
                    <span className="text-[9px] text-muted-foreground leading-tight">{monthsInQuarter.join(' ')}</span>
                  </div>
                  <div className="flex gap-1.5 flex-1">
                    {quarterWeeks.map(week => {
                      const bin = intensity(week.margin_recovered)
                      const cls = BIN_CLASSES[bin]
                      const disabled = !week.has_production
                      return (
                        <Tooltip key={week.week_id}>
                          <TooltipTrigger asChild>
                            <button
                              onClick={() => handleClick(week)}
                              disabled={disabled}
                              aria-label={week.week_id}
                              className={`h-8 flex-1 min-w-[18px] rounded-md border transition-all ${cls} ${
                                disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:scale-110 hover:shadow-md'
                              }`}
                            />
                          </TooltipTrigger>
                          <TooltipContent side="top" className="text-xs">
                            <WeekTooltip week={week} />
                          </TooltipContent>
                        </Tooltip>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </TooltipProvider>
      </CardContent>
    </Card>
  )
}

function WeekTooltip({ week }: { week: WeekImpact }) {
  if (!week.has_production) {
    return (
      <div className="space-y-0.5">
        <p className="font-mono font-semibold">{week.week_id}</p>
        <p className="text-muted-foreground">No production · cleaning / vacation</p>
      </div>
    )
  }
  return (
    <div className="space-y-1 min-w-[180px]">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono font-semibold">{week.week_id}</span>
        <span className="text-[10px] text-muted-foreground">
          {formatDate(week.week_start)} – {formatDate(week.week_end)}
        </span>
      </div>
      <div className="flex items-center justify-between gap-3 pt-1 border-t border-border/40">
        <span className="text-muted-foreground">Margin recoverable</span>
        <span className="tabular-nums font-bold text-emerald-700">€{week.margin_recovered.toLocaleString()}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">Hours saved</span>
        <span className="tabular-nums font-semibold">{week.hours_recovered.toFixed(1)} h</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">SKUs recovered</span>
        <span className="tabular-nums font-semibold">{week.dropped_skus_recovered}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">OEE uplift</span>
        <span className="tabular-nums font-semibold">+{week.oee_uplift_pp.toFixed(1)} pp</span>
      </div>
      <p className="text-[10px] text-muted-foreground pt-1 italic">Click to open Compare view</p>
    </div>
  )
}

function Legend() {
  return (
    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
      <span>Less</span>
      <div className="flex gap-1">
        {[0, 1, 2, 3, 4].map(b => (
          <span key={b} className={`h-3 w-3 rounded-sm border ${BIN_CLASSES[b]}`} />
        ))}
      </div>
      <span>More</span>
    </div>
  )
}
