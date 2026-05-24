'use client'

import { useRouter } from 'next/navigation'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ChevronRight } from 'lucide-react'
import type { ImpactAtlas, WeekImpact } from '@/lib/types/insights'

interface ImpactRankedListProps {
  atlas: ImpactAtlas
  limit?: number
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + 'T00:00:00Z')
  const e = new Date(end + 'T00:00:00Z')
  const fmt = (d: Date, withMonth: boolean) =>
    d.toLocaleDateString('en-GB', { day: 'numeric', month: withMonth ? 'short' : undefined, timeZone: 'UTC' })
  const sameMonth = s.getUTCMonth() === e.getUTCMonth()
  return sameMonth ? `${fmt(s, false)}–${fmt(e, true)}` : `${fmt(s, true)} – ${fmt(e, true)}`
}

export function ImpactRankedList({ atlas, limit = 10 }: ImpactRankedListProps) {
  const router = useRouter()
  const ranked = [...atlas.weeks]
    .filter(w => w.has_production)
    .sort((a, b) => b.margin_recovered - a.margin_recovered)
    .slice(0, limit)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b py-3">
        <CardTitle className="text-base">Top {limit} weeks — biggest recovery opportunity</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">
          Sorted by margin LineWise would have protected. Click any row to drill into the side-by-side comparison.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y">
          {ranked.map((week, i) => (
            <RankedRow
              key={week.week_id}
              week={week}
              rank={i + 1}
              onClick={() => router.push(`/compare?week_id=${week.week_id}`)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function RankedRow({ week, rank, onClick }: { week: WeekImpact; rank: number; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-4 px-4 py-3 hover:bg-muted/40 transition-colors text-left"
    >
      <span className="text-xs font-bold tabular-nums text-muted-foreground w-7 shrink-0 text-center">
        #{rank}
      </span>

      <div className="flex flex-col min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold">{week.week_id}</span>
          <span className="text-xs text-muted-foreground">{formatDateRange(week.week_start, week.week_end)}</span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <Badge variant="outline" className="text-[10px] py-0 px-1.5 h-4">
            real OEE {(week.real_oee * 100).toFixed(1)}%
          </Badge>
          <span className="text-[10px] text-emerald-700 font-medium">
            +{week.oee_uplift_pp.toFixed(1)} pp uplift
          </span>
        </div>
      </div>

      <div className="hidden sm:flex flex-col items-end shrink-0">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Changeover</span>
        <span className="tabular-nums text-sm font-semibold">{week.hours_recovered.toFixed(1)} h</span>
      </div>

      <div className="hidden md:flex flex-col items-end shrink-0">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">SKUs</span>
        <span className="tabular-nums text-sm font-semibold">{week.dropped_skus_recovered}</span>
      </div>

      <div className="flex flex-col items-end shrink-0 min-w-[88px]">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Margin</span>
        <span className="tabular-nums text-base font-bold text-emerald-700">
          €{week.margin_recovered.toLocaleString()}
        </span>
      </div>

      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
    </button>
  )
}
