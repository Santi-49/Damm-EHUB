// Daily OEE overlay for the compare page — actual vs planned per day.
//
// Each column is one day. The filled bar is the actual OEE; the dashed tick is
// the planned OEE. Colour bins:
//   green ≥ 60% · amber 40–60% · red < 40%.

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { dailyOee } from '@/lib/fixtures/oee-overlay'

function binClasses(oee: number): { bar: string; text: string } {
  if (oee >= 0.6) return { bar: 'bg-emerald-500',     text: 'text-white' }
  if (oee >= 0.4) return { bar: 'bg-amber-500',       text: 'text-white' }
  return { bar: 'bg-red-500', text: 'text-white' }
}

export function OeeOverlay() {
  const worst = dailyOee.reduce(
    (acc, d) => (d.oee_actual < acc.oee_actual ? d : acc),
    dailyOee[0],
  )

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b py-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-base">OEE timeline overlay — actual vs planned</CardTitle>
          <Badge variant="secondary" className="text-[10px]">Post-mortem</Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Filled bar = actual · dashed tick = planned · red &lt; 40% · amber 40–60% · green ≥ 60%
        </p>
      </CardHeader>
      <CardContent className="pt-4 pb-3">
        <div className="grid grid-cols-7 gap-2">
          {dailyOee.map(d => {
            const { bar, text } = binClasses(d.oee_actual)
            const actualPct = Math.max(8, d.oee_actual * 100)
            const plannedPct = d.oee_planned * 100
            return (
              <div key={d.short} className="flex flex-col items-center">
                <div className="text-[10px] text-muted-foreground mb-1.5">{d.short}</div>
                <div
                  className="relative w-full bg-muted/30 rounded-md overflow-hidden"
                  style={{ height: 80 }}
                >
                  <div
                    className="absolute left-0 right-0 border-t-2 border-dashed border-foreground/50 z-10"
                    style={{ bottom: `${plannedPct}%` }}
                  >
                    <span className="absolute right-0.5 -top-3.5 text-[8px] text-muted-foreground tabular-nums">
                      {(d.oee_planned * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div
                    className={`absolute left-0 right-0 bottom-0 ${bar} rounded-md flex items-end justify-center pb-1 transition-all`}
                    style={{ height: `${actualPct}%` }}
                  >
                    <span className={`text-[10px] font-semibold ${text} tabular-nums`}>
                      {(d.oee_actual * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <div className="mt-4 text-xs text-muted-foreground leading-relaxed">
          Worst day: <strong className="text-foreground">{worst.day}</strong> at{' '}
          <span className="tabular-nums">{(worst.oee_actual * 100).toFixed(0)}%</span>{' '}
          — unplanned maintenance stacked with a "Referencia" changeover. Structural risk visible across the 2025 history.
        </div>
      </CardContent>
    </Card>
  )
}
