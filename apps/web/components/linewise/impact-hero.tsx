import { Card } from '@/components/ui/card'
import { CalendarRange, Clock, Euro, ShieldCheck, TrendingUp } from 'lucide-react'
import type { ImpactAtlas } from '@/lib/types/insights'

interface ImpactHeroProps {
  atlas: ImpactAtlas
}

export function ImpactHero({ atlas }: ImpactHeroProps) {
  const tiles = [
    {
      icon: Euro,
      heading: `€${(atlas.total_margin_recovered / 1_000_000).toFixed(2)}M`,
      label: 'margin Damm left on the table',
      sub: `${atlas.total_dropped_skus_recovered} SKUs would not have been dropped`,
      tone: 'text-emerald-700 bg-emerald-50 border-emerald-200',
      isHeadline: true,
    },
    {
      icon: Clock,
      heading: `${atlas.total_hours_recovered.toFixed(0)} h`,
      label: 'changeover waste recoverable',
      sub: `Across ${atlas.weeks_with_production} production weeks`,
      tone: 'text-blue-700 bg-blue-50 border-blue-200',
    },
    {
      icon: TrendingUp,
      heading: `+${atlas.avg_oee_uplift_pp.toFixed(1)} pp`,
      label: 'average OEE uplift per week',
      sub: 'Same demand, same incidents — fairly compared',
      tone: 'text-amber-700 bg-amber-50 border-amber-200',
    },
    {
      icon: CalendarRange,
      heading: `${atlas.weeks_with_production}/52`,
      label: 'weeks audited',
      sub: `${52 - atlas.weeks_with_production} non-producing weeks excluded`,
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
              €{(atlas.total_margin_recovered / 1_000_000).toFixed(2)}M of margin recoverable in {atlas.year}
            </h2>
            <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
              We replayed every production week of {atlas.year} through LineWise, holding incidents and calendar constant.
              The numbers below are what the historical execution left on the table.
            </p>
          </div>
        </div>
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
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
