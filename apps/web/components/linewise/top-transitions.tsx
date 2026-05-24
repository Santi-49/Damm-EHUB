'use client'

import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { Sequence, Slot } from '@/lib/types/linewise'
import { SlotDrawer } from './slot-drawer'

interface TransitionRow {
  realSlot: Slot
  optSlot: Slot | null
  actualH: number
  optH: number | null
  overrunH: number
  line: number
}

function buildTopRows(real: Sequence, opt: Sequence, n = 3): TransitionRow[] {
  const optChangeovers = opt.slots.filter(s => s.kind === 'changeover')

  return real.slots
    .filter(s => s.kind === 'changeover' && s.changeover_h != null)
    .map(rs => {
      const match = optChangeovers.find(os => os.line === rs.line && os.sku === rs.sku) ?? null
      const actualH = rs.changeover_h!
      const optH = match?.changeover_h ?? null
      const overrunH = optH != null ? +(actualH - optH).toFixed(2) : 0
      return { realSlot: rs, optSlot: match, actualH, optH, overrunH, line: rs.line }
    })
    .sort((a, b) => b.overrunH - a.overrunH)
    .slice(0, n)
}

interface TopTransitionsProps {
  real: Sequence
  opt: Sequence
}

export function TopTransitions({ real, opt }: TopTransitionsProps) {
  const [selected, setSelected] = useState<Slot | null>(null)
  const rows = buildTopRows(real, opt)

  if (rows.length === 0) return null

  return (
    <>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Top 3 costliest transitions — what LineWise avoids</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Click any card to see the full driver breakdown</p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {rows.map((row, i) => (
            <TransitionCard
              key={row.realSlot.id}
              row={row}
              rank={i + 1}
              onClick={() => setSelected(row.realSlot)}
            />
          ))}
        </div>
      </div>
      <SlotDrawer slot={selected} onClose={() => setSelected(null)} />
    </>
  )
}

function TransitionCard({
  row,
  rank,
  onClick,
}: {
  row: TransitionRow
  rank: number
  onClick: () => void
}) {
  const isHighOverrun = row.overrunH >= 1
  const borderClass = isHighOverrun
    ? 'border-red-200 bg-red-50/60 hover:bg-red-50'
    : 'border-amber-200 bg-amber-50/60 hover:bg-amber-50'

  const drivers = row.realSlot.changeover_drivers ?? []

  return (
    <button
      className={`rounded-xl border p-4 text-left w-full transition-colors cursor-pointer ${borderClass}`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          #{rank} worst overrun
        </span>
        <Badge variant="outline" className="text-xs">L{row.line}</Badge>
      </div>

      <p className="text-sm font-semibold leading-snug mb-4 text-foreground line-clamp-2">
        {row.realSlot.label ?? row.realSlot.sku ?? '—'}
      </p>

      <div className="flex items-center gap-2 mb-1">
        <span className="tabular-nums text-2xl font-bold text-red-700 leading-none">
          {row.actualH} h
        </span>
        <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
        <span className="tabular-nums text-2xl font-bold text-emerald-700 leading-none">
          {row.optH != null ? `${row.optH} h` : '—'}
        </span>
      </div>

      {row.overrunH > 0 && (
        <p className="text-xs font-semibold text-red-700 mb-3">
          +{row.overrunH} h overrun eliminated
        </p>
      )}

      {drivers.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {drivers.slice(0, 3).map(d => (
            <span
              key={d.feature}
              className="rounded-full bg-background/80 border px-2 py-0.5 text-[10px] font-medium"
            >
              {d.feature.replace(/_/g, ' ')} +{d.impact_h} h
            </span>
          ))}
        </div>
      )}
    </button>
  )
}
