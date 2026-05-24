import type { ReplanScenario } from '@/lib/fixtures/replan-scenarios'
import type { SimulationReport } from '@/lib/types/linewise'
import { CheckCircle2, TrendingDown, Clock, AlertTriangle, ArrowRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface RecommendationCardProps {
  scenario: ReplanScenario
}

function delta(base: SimulationReport, replan: SimulationReport) {
  return {
    oee_pp:      +((replan.oee_global - base.oee_global) * 100).toFixed(1),
    h_changes:   +(replan.h_changes - base.h_changes).toFixed(1),
    h_productive: +(replan.h_productive - base.h_productive).toFixed(1),
    coverage:    +((replan.coverage - base.coverage) * 100).toFixed(0),
  }
}

export function RecommendationCard({ scenario }: RecommendationCardProps) {
  const { recommendation: rec, report, base } = scenario
  const d = delta(base, report)

  const impactTiles = [
    {
      icon: TrendingDown,
      color: d.oee_pp >= 0 ? 'text-emerald-600' : 'text-amber-600',
      value: `${d.oee_pp >= 0 ? '+' : ''}${d.oee_pp} pp`,
      label: 'OEE impact',
      sub: `${(base.oee_global * 100).toFixed(1)}% → ${(report.oee_global * 100).toFixed(1)}%`,
    },
    {
      icon: Clock,
      color: d.h_changes <= 0 ? 'text-emerald-600' : 'text-amber-600',
      value: `${d.h_changes >= 0 ? '+' : ''}${d.h_changes} h`,
      label: 'Changeover time',
      sub: `${base.h_changes} h → ${report.h_changes} h`,
    },
    {
      icon: CheckCircle2,
      color: d.coverage >= 0 ? 'text-emerald-600' : 'text-amber-600',
      value: `${d.coverage >= 0 ? '+' : ''}${d.coverage} pp`,
      label: 'Coverage delta',
      sub: `${(base.coverage * 100).toFixed(0)}% → ${(report.coverage * 100).toFixed(0)}%`,
    },
  ]

  return (
    <div className="rounded-xl border-2 border-primary/20 bg-primary/5 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-primary/15 flex items-start gap-3">
        <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0 mt-0.5">
          <ArrowRight className="h-4 w-4 text-white" />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary/70 mb-0.5">
            LineWise Recommendation
          </p>
          <p className="text-lg font-bold leading-snug">{rec.headline}</p>
          {rec.assignedLine && (
            <Badge className="mt-1.5 bg-primary text-white text-xs">L{rec.assignedLine} assigned</Badge>
          )}
        </div>
      </div>

      {/* Why */}
      <div className="px-5 py-4 border-b border-primary/10">
        <p className="text-sm text-foreground/80 leading-relaxed">{rec.why}</p>
        <div className="mt-3 space-y-1">
          {rec.constraints.map(c => (
            <div key={c} className="flex items-center gap-2 text-xs text-muted-foreground">
              <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 flex-shrink-0" />
              {c}
            </div>
          ))}
        </div>
      </div>

      {/* Impact strip */}
      <div className="grid grid-cols-3 divide-x divide-primary/10">
        {impactTiles.map(t => (
          <div key={t.label} className="px-4 py-3 text-center">
            <p className={`text-xl font-bold tabular-nums ${t.color}`}>{t.value}</p>
            <p className="text-xs font-medium text-foreground/70 mt-0.5">{t.label}</p>
            <p className="text-xs text-muted-foreground">{t.sub}</p>
          </div>
        ))}
      </div>

      {/* Dropped SKUs warning */}
      {report.dropped_skus.length > 0 && (
        <div className="px-5 py-3 border-t border-amber-200 bg-amber-50 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-800">
            <span className="font-semibold">Capacity shortfall: </span>
            {report.dropped_skus.map(d => (
              <span key={d.sku}>
                {d.sku} ({d.units_dropped.toLocaleString()} units · €{d.margin_lost.toLocaleString()})
              </span>
            )).reduce((acc, el, i) => i === 0 ? [el] : [...acc, ', ', el], [] as React.ReactNode[])}
          </div>
        </div>
      )}
    </div>
  )
}
