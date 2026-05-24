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
    .sort((a, b) => b.clean_saving_h - a.clean_saving_h)
    .slice(0, limit)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b py-3">
        <CardTitle className="text-base">Top {limit} windows — biggest clean savings</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">
          Sorted by raw v2 vs real simulated makespan. Click any row to drill into the side-by-side comparison.
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
            {week.node_count} nodes
          </Badge>
          <span className="text-[10px] text-muted-foreground font-medium">
            v2 {week.v2_makespan_h.toFixed(1)} h · real {week.real_simulated_makespan_h.toFixed(1)} h
          </span>
        </div>
      </div>

      <div className="hidden sm:flex flex-col items-end shrink-0">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Adjusted</span>
        <span
          className={`tabular-nums text-sm font-semibold ${
            week.adjusted_saving_h >= 0 ? 'text-emerald-700' : 'text-red-700'
          }`}
        >
          {week.adjusted_saving_h.toFixed(1)} h
        </span>
      </div>

      <div className="hidden md:flex flex-col items-end shrink-0">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Cleaning</span>
        <span className="tabular-nums text-sm font-semibold">{week.real_cleaning_h.toFixed(1)} h</span>
      </div>

      <div className="flex flex-col items-end shrink-0 min-w-[88px]">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Clean</span>
        <span className="tabular-nums text-base font-bold text-emerald-700">
          {week.clean_saving_h.toFixed(1)} h
        </span>
      </div>

      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
    </button>
  )
}
