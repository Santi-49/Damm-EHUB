import type { SimulationReport, DeltaMetrics } from '@/lib/types/linewise'
import { Card, CardContent } from '@/components/ui/card'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface KpiStripProps {
  report: SimulationReport
  delta?: DeltaMetrics
}

export function KpiStrip({ report, delta }: KpiStripProps) {
  const tiles: {
    label:    string
    value:    string
    sub?:     string
    trend?:   number
    trendFmt?: string
  }[] = [
    {
      label:    'OEE Global',
      value:    `${(report.oee_global * 100).toFixed(1)}%`,
      trend:    delta?.oee_pp,
      trendFmt: delta ? `${delta.oee_pp >= 0 ? '+' : ''}${(delta.oee_pp * 100).toFixed(1)} pp vs real` : undefined,
    },
    {
      label: 'Changeover hours',
      value: `${report.h_changes} h`,
      trend:    delta ? -delta.h_changes_saved : undefined,
      trendFmt: delta ? `${delta.h_changes_saved >= 0 ? '−' : '+'}${Math.abs(delta.h_changes_saved)} h vs real` : undefined,
    },
    {
      label: 'Productive hours',
      value: `${report.h_productive} h`,
      trend:    delta?.h_productive_gained,
      trendFmt: delta ? `${delta.h_productive_gained >= 0 ? '+' : ''}${delta.h_productive_gained} h vs real` : undefined,
    },
    {
      label: 'Coverage',
      value: `${(report.coverage * 100).toFixed(0)}%`,
      trend:    delta?.coverage_delta,
      trendFmt: delta ? `${delta.coverage_delta >= 0 ? '+' : ''}${(delta.coverage_delta * 100).toFixed(0)} pp vs real` : undefined,
    },
    {
      label: 'Dropped SKUs',
      value: report.dropped_skus.length === 0 ? 'None' : `${report.dropped_skus.length}`,
      sub:   report.dropped_skus.length > 0
        ? `€${report.dropped_skus.reduce((s, d) => s + d.margin_lost, 0).toLocaleString()} margin at risk`
        : 'Full coverage',
      trend: report.dropped_skus.length === 0 ? 1 : -1,
    },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {tiles.map(tile => (
        <Card key={tile.label} className="bg-card">
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground font-medium mb-1">{tile.label}</p>
            <p className="text-2xl font-bold tabular-nums tracking-tight">{tile.value}</p>
            {(tile.trendFmt ?? tile.sub) && (
              <div className="flex items-center gap-1 mt-1">
                <TrendIcon trend={tile.trend} />
                <span className="text-xs text-muted-foreground">{tile.trendFmt ?? tile.sub}</span>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function TrendIcon({ trend }: { trend?: number }) {
  if (trend == null) return null
  if (trend > 0) return <TrendingUp className="h-3 w-3 text-emerald-600 flex-shrink-0" />
  if (trend < 0) return <TrendingDown className="h-3 w-3 text-red-500 flex-shrink-0" />
  return <Minus className="h-3 w-3 text-muted-foreground flex-shrink-0" />
}
