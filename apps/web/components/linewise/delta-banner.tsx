import type { DeltaMetrics, SimulationReport } from '@/lib/types/linewise'
import { TrendingUp, Clock, CheckCircle2, AlertCircle } from 'lucide-react'

interface DeltaBannerProps {
  opt:   SimulationReport
  real:  SimulationReport
  delta: DeltaMetrics
}

export function DeltaBanner({ opt, real, delta }: DeltaBannerProps) {
  const marginSaved = real.dropped_skus.reduce((s, d) => s + d.margin_lost, 0)

  const tiles = [
    {
      icon:    TrendingUp,
      color:   'text-emerald-600',
      bg:      'bg-emerald-50 border-emerald-200',
      heading: `+${(delta.oee_pp * 100).toFixed(1)} pp`,
      label:   'OEE improvement',
      sub:     `${(real.oee_global * 100).toFixed(1)}% → ${(opt.oee_global * 100).toFixed(1)}%`,
    },
    {
      icon:    Clock,
      color:   'text-amber-600',
      bg:      'bg-amber-50 border-amber-200',
      heading: `−${delta.h_changes_saved} h`,
      label:   'Changeover time saved',
      sub:     `${real.h_changes} h → ${opt.h_changes} h`,
    },
    {
      icon:    CheckCircle2,
      color:   'text-blue-600',
      bg:      'bg-blue-50 border-blue-200',
      heading: `+${delta.h_productive_gained} h`,
      label:   'Productive hours gained',
      sub:     `${real.h_productive} h → ${opt.h_productive} h`,
    },
    {
      icon:    AlertCircle,
      color:   'text-primary',
      bg:      'bg-primary/5 border-primary/20',
      heading: marginSaved > 0 ? `€${marginSaved.toLocaleString()}` : '0 drops',
      label:   marginSaved > 0 ? 'Margin recovered' : 'No SKUs dropped',
      sub:     marginSaved > 0
        ? `${real.dropped_skus.length} SKU${real.dropped_skus.length > 1 ? 's' : ''} recovered`
        : 'Full coverage in S_opt',
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {tiles.map(t => (
        <div key={t.label} className={`rounded-xl border p-4 flex gap-3 items-start ${t.bg}`}>
          <t.icon className={`h-5 w-5 mt-0.5 flex-shrink-0 ${t.color}`} />
          <div className="min-w-0">
            <p className={`text-xl font-bold tabular-nums leading-tight ${t.color}`}>{t.heading}</p>
            <p className="text-xs font-medium text-foreground/80 mt-0.5">{t.label}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{t.sub}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
