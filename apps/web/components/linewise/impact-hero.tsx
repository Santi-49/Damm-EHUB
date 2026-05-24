import { Card } from '@/components/ui/card'
import { CalendarRange, Clock, Gauge, ShieldCheck, TrendingUp } from 'lucide-react'
import type { ImpactAtlas } from '@/lib/types/insights'

interface ImpactHeroProps {
  atlas: ImpactAtlas
}

export function ImpactHero({ atlas }: ImpactHeroProps) {
  const tiles = [
    {
      icon: Clock,
      heading: `${atlas.clean_saving_h_per_week.toFixed(1)} h/wk`,
      label: 'clean routing savings',
      sub: `Raw v2 vs real simulated makespan`,
      tone: 'text-emerald-700 bg-emerald-50 border-emerald-200',
      isHeadline: true,
    },
    {
      icon: TrendingUp,
      heading: `${atlas.adjusted_saving_h_per_week.toFixed(1)} h/wk`,
      label: 'adjusted stress-test savings',
      sub: `${atlas.adjusted_weeks_won}/${atlas.windows_evaluated} windows still win`,
      tone: 'text-blue-700 bg-blue-50 border-blue-200',
    },
    {
      icon: ShieldCheck,
      heading: `${atlas.valid_solutions}/${atlas.windows_evaluated}`,
      label: 'valid optimizer solutions',
      sub: 'Every demand node visited once; no drops',
      tone: 'text-amber-700 bg-amber-50 border-amber-200',
    },
    {
      icon: Gauge,
      heading: `${atlas.mean_v2_makespan_h.toFixed(1)} h`,
      label: 'mean v2 makespan',
      sub: `Real simulated baseline ${atlas.mean_real_simulated_makespan_h.toFixed(1)} h`,
      tone: 'text-red-700 bg-red-50 border-red-200',
    },
    {
      icon: CalendarRange,
      heading: `${atlas.maintenance_adjusted_saving_h_per_week.toFixed(1)} h/wk`,
      label: 'maintenance replay savings',
      sub: `${atlas.maintenance_adjusted_weeks_won}/${atlas.windows_evaluated} windows still win`,
      tone: 'text-muted-foreground bg-muted/30 border-muted',
    },
  ]

  return (
    <Card className="overflow-hidden">
      <div className="border-b bg-muted/20 px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary/10 p-2 mt-0.5">
            <ShieldCheck className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">
              {atlas.clean_saving_h_per_week.toFixed(1)} h/week clean routing savings in the {atlas.year} replay
            </h2>
            <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
              The benchmark now uses the optimizer v2 report directly: {atlas.windows_evaluated} weekly windows,
              {' '}{atlas.valid_solutions} valid solutions, a pessimistic adjusted result of{' '}
              {atlas.adjusted_saving_h_per_week.toFixed(1)} h/week, and a mixed observed check of{' '}
              {atlas.mixed_observed_saving_h_per_week.toFixed(1)} h/week.
            </p>
          </div>
        </div>
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-5">
        {tiles.map(tile => (
          <div key={tile.label} className={`rounded-xl border p-4 ${tile.tone}`}>
            <tile.icon className="mb-3 h-5 w-5" />
            <p className={`tabular-nums font-bold leading-none ${tile.isHeadline ? 'text-3xl' : 'text-2xl'}`}>
              {tile.heading}
            </p>
            <p className="mt-1 text-sm font-semibold">{tile.label}</p>
            <p className="mt-1 text-xs opacity-80">{tile.sub}</p>
          </div>
        ))}
      </div>
    </Card>
  )
}
