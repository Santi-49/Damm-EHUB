'use client'

import { useState } from 'react'
import type { Sequence, Slot } from '@/lib/types/linewise'
import { Badge } from '@/components/ui/badge'
import { SlotDrawer } from './slot-drawer'
import { ChevronDown, ChevronUp, Minus } from 'lucide-react'

interface ChangeoverRow {
  realSlot:    Slot
  optSlot:     Slot | null
  actualH:     number
  optH:        number | null
  overrunH:    number
  line:        number
  fromSku:     string
  label:       string
}

function buildRows(real: Sequence, opt: Sequence): ChangeoverRow[] {
  const realChangeovers = real.slots.filter(s => s.kind === 'changeover' && s.changeover_h != null)
  const optChangeovers  = opt.slots.filter(s => s.kind === 'changeover')

  return realChangeovers
    .map(rs => {
      // Match by line + from-SKU
      const match = optChangeovers.find(os => os.line === rs.line && os.sku === rs.sku) ?? null
      const actualH  = rs.changeover_h!
      const optH     = match?.changeover_h ?? null
      const overrunH = optH != null ? +(actualH - optH).toFixed(2) : 0

      return {
        realSlot: rs,
        optSlot:  match,
        actualH,
        optH,
        overrunH,
        line:    rs.line,
        fromSku: rs.sku ?? '—',
        label:   rs.label ?? rs.sku ?? '—',
      } satisfies ChangeoverRow
    })
    .sort((a, b) => b.overrunH - a.overrunH)
}

type SortKey = 'overrunH' | 'actualH' | 'line'

interface ChangeoverTableProps {
  real: Sequence
  opt:  Sequence
}

export function ChangeoverTable({ real, opt }: ChangeoverTableProps) {
  const [sortKey,  setSortKey]  = useState<SortKey>('overrunH')
  const [sortAsc,  setSortAsc]  = useState(false)
  const [selected, setSelected] = useState<Slot | null>(null)

  const rows = buildRows(real, opt)
  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey] ?? 0
    const bv = b[sortKey] ?? 0
    return sortAsc ? av - bv : bv - av
  })

  const cycle = (key: SortKey) => {
    if (sortKey === key) setSortAsc(v => !v)
    else { setSortKey(key); setSortAsc(false) }
  }

  const Icon = ({ k }: { k: SortKey }) => {
    if (sortKey !== k) return <Minus className="h-3 w-3 opacity-30" />
    return sortAsc
      ? <ChevronUp   className="h-3 w-3" />
      : <ChevronDown className="h-3 w-3" />
  }

  return (
    <>
      <div className="rounded-xl border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30 flex items-center justify-between">
          <span className="text-sm font-medium">Changeover comparison — real vs proposal</span>
          <span className="text-xs text-muted-foreground">Click a row to inspect drivers</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/10 text-xs text-muted-foreground">
                <Th onClick={() => cycle('line')} icon={<Icon k="line" />}>Line</Th>
                <th className="px-3 py-2 text-left font-medium">Transition</th>
                <Th onClick={() => cycle('actualH')} icon={<Icon k="actualH" />}>Real</Th>
                <th className="px-3 py-2 text-right font-medium">S_opt</th>
                <Th onClick={() => cycle('overrunH')} icon={<Icon k="overrunH" />}>Overrun</Th>
                <th className="px-3 py-2 text-left font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => (
                <tr
                  key={row.realSlot.id}
                  className={`border-b last:border-0 cursor-pointer hover:bg-muted/30 transition-colors ${i % 2 === 0 ? '' : 'bg-muted/10'}`}
                  onClick={() => setSelected(row.realSlot)}
                >
                  <td className="px-3 py-2 text-center">
                    <Badge variant="outline" className="text-xs">L{row.line}</Badge>
                  </td>
                  <td className="px-3 py-2 max-w-[220px] truncate font-medium">
                    {row.label}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium">
                    {row.actualH} h
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {row.optH != null ? `${row.optH} h` : '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <OverrunBadge h={row.overrunH} />
                  </td>
                  <td className="px-3 py-2">
                    <SourceBadge source={row.realSlot.changeover_source} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <SlotDrawer slot={selected} onClose={() => setSelected(null)} />
    </>
  )
}

function Th({ children, onClick, icon }: { children: React.ReactNode; onClick: () => void; icon: React.ReactNode }) {
  return (
    <th
      className="px-3 py-2 text-right font-medium cursor-pointer select-none hover:text-foreground"
      onClick={onClick}
    >
      <span className="inline-flex items-center gap-1 justify-end">
        {children}
        {icon}
      </span>
    </th>
  )
}

function OverrunBadge({ h }: { h: number }) {
  if (h <= 0)   return <span className="text-emerald-600 font-medium tabular-nums">on time</span>
  if (h < 0.5)  return <span className="text-amber-500 font-medium tabular-nums">+{h} h</span>
  return <span className="text-red-600 font-bold tabular-nums">+{h} h</span>
}

function SourceBadge({ source }: { source?: string }) {
  if (!source) return null
  const map: Record<string, string> = {
    ml:       'bg-blue-100 text-blue-700 border-blue-200',
    teorico:  'bg-amber-100 text-amber-700 border-amber-200',
    hibrido:  'bg-purple-100 text-purple-700 border-purple-200',
  }
  return (
    <Badge variant="outline" className={`text-[10px] ${map[source] ?? ''}`}>
      {source}
    </Badge>
  )
}
