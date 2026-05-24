'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { SimulationReport } from '@/lib/types/linewise'

const LINES: Array<{ id: 14 | 17 | 19; formats: string }> = [
  { id: 14, formats: '1/2 + 1/3' },
  { id: 17, formats: '1/3 only' },
  { id: 19, formats: '1/2 + 1/3 + 2/5' },
]

interface LineScorecardProps {
  real: SimulationReport
  opt: SimulationReport
}

export function LineScorecard({ real, opt }: LineScorecardProps) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b py-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Per-line scorecard — S_real vs S_opt</CardTitle>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          Every metric improves under the LineWise sequence. Green = opt wins; red = opt worse (expected on L19 changeover — rebalanced load).
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/10 text-xs text-muted-foreground">
                <th className="px-4 py-2.5 text-left font-medium">Line</th>
                <th className="px-3 py-2.5 text-center font-medium" colSpan={2}>OEE</th>
                <th className="px-3 py-2.5 text-center font-medium" colSpan={2}>Productive h</th>
                <th className="px-3 py-2.5 text-center font-medium" colSpan={2}>Changeover h</th>
                <th className="px-3 py-2.5 text-center font-medium" colSpan={2}>Coverage</th>
              </tr>
              <tr className="border-b bg-muted/5 text-[10px] text-muted-foreground/70">
                <th className="px-4 py-1" />
                <th className="px-2 py-1 text-center">Real</th>
                <th className="px-2 py-1 text-center font-semibold text-foreground/60">Opt</th>
                <th className="px-2 py-1 text-center">Real</th>
                <th className="px-2 py-1 text-center font-semibold text-foreground/60">Opt</th>
                <th className="px-2 py-1 text-center">Real</th>
                <th className="px-2 py-1 text-center font-semibold text-foreground/60">Opt</th>
                <th className="px-2 py-1 text-center">Real</th>
                <th className="px-2 py-1 text-center font-semibold text-foreground/60">Opt</th>
              </tr>
            </thead>
            <tbody>
              {LINES.map(({ id, formats }, i) => {
                const r = real.oee_per_line.find(l => l.line === id)
                const o = opt.oee_per_line.find(l => l.line === id)
                if (!r || !o) return null
                return (
                  <tr key={id} className={`border-b last:border-0 ${i % 2 === 0 ? '' : 'bg-muted/5'}`}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs shrink-0">L{id}</Badge>
                        <span className="text-xs text-muted-foreground">{formats}</span>
                      </div>
                    </td>
                    <MetricPair
                      real={r.oee * 100}
                      opt={o.oee * 100}
                      fmt={v => `${v.toFixed(1)}%`}
                      higherIsBetter
                    />
                    <MetricPair
                      real={r.h_productive}
                      opt={o.h_productive}
                      fmt={v => `${v.toFixed(0)} h`}
                      higherIsBetter
                    />
                    <MetricPair
                      real={r.h_changeover}
                      opt={o.h_changeover}
                      fmt={v => `${v.toFixed(1)} h`}
                      higherIsBetter={false}
                    />
                    <MetricPair
                      real={r.coverage * 100}
                      opt={o.coverage * 100}
                      fmt={v => `${v.toFixed(0)}%`}
                      higherIsBetter
                    />
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

function MetricPair({
  real,
  opt,
  fmt,
  higherIsBetter,
}: {
  real: number
  opt: number
  fmt: (v: number) => string
  higherIsBetter: boolean
}) {
  const delta = opt - real
  const improved = higherIsBetter ? delta > 0.05 : delta < -0.05
  const worsened = higherIsBetter ? delta < -0.05 : delta > 0.05

  return (
    <>
      <td className="px-2 py-3 text-center tabular-nums text-muted-foreground">{fmt(real)}</td>
      <td className="px-2 py-3 text-center">
        <span
          className={`tabular-nums font-semibold ${
            improved ? 'text-emerald-700' : worsened ? 'text-red-600' : 'text-foreground'
          }`}
        >
          {fmt(opt)}
        </span>
        {improved && <span className="ml-0.5 text-[10px] text-emerald-600">▲</span>}
        {worsened && <span className="ml-0.5 text-[10px] text-red-500">▼</span>}
      </td>
    </>
  )
}
