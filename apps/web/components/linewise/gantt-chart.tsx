'use client'

import { useState } from 'react'
import type { Sequence, Slot, Line } from '@/lib/types/linewise'
import { SlotDrawer } from './slot-drawer'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const LINES: Line[] = [14, 17, 19]

// Color map per slot kind / SKU family — all with white text
const getSlotStyle = (slot: Slot): string => {
  if (slot.kind === 'changeover')  return 'bg-amber-400 text-amber-950 ring-inset ring-1 ring-amber-300/50'
  if (slot.kind === 'cleaning')    return 'bg-[oklch(0.55_0.1_240)] text-white ring-inset ring-1 ring-white/10'
  if (slot.kind === 'maintenance') return 'bg-[oklch(0.45_0.04_250)] text-white ring-inset ring-1 ring-white/10'

  // production — colour by SKU family
  const prefix = slot.sku?.split('-')[0] ?? ''
  const map: Record<string, string> = {
    DAMM:  'bg-[oklch(0.513_0.212_23.4)] text-white ring-inset ring-1 ring-white/10',
    ESTB:  'bg-[oklch(0.46_0.18_23.4)] text-white ring-inset ring-1 ring-white/10',
    DAURA: 'bg-[oklch(0.55_0.16_28)] text-white ring-inset ring-1 ring-white/10',
    LEMO:  'bg-[oklch(0.60_0.13_85)] text-white ring-inset ring-1 ring-white/10',
    FREQ:  'bg-[oklch(0.55_0.13_145)] text-white ring-inset ring-1 ring-white/10',
    RDSQ:  'bg-[oklch(0.44_0.15_340)] text-white ring-inset ring-1 ring-white/10',
    VOLL:  'bg-[oklch(0.38_0.17_23.4)] text-white ring-inset ring-1 ring-white/10',
  }
  return map[prefix] ?? 'bg-primary text-white ring-inset ring-1 ring-white/10'
}

function parseHour(iso: string, weekStart: string): number {
  return (new Date(iso).getTime() - new Date(weekStart).getTime()) / (1000 * 60 * 60)
}

function formatDuration(start: string, end: string): string {
  const h = (new Date(end).getTime() - new Date(start).getTime()) / (1000 * 60 * 60)
  return h >= 1 ? `${h.toFixed(1)} h` : `${Math.round(h * 60)} min`
}

function formatTooltip(slot: Slot): { title: string; lines: string[] } {
  const duration = formatDuration(slot.start, slot.end)
  if (slot.kind === 'production') {
    const lines: string[] = [`Duration: ${duration}`]
    if (slot.units)       lines.push(`Units: ${slot.units.toLocaleString()}`)
    if (slot.oee_actual != null)   lines.push(`OEE actual: ${(slot.oee_actual * 100).toFixed(1)}%`)
    if (slot.oee_expected != null) lines.push(`OEE expected: ${(slot.oee_expected * 100).toFixed(1)}%`)
    return { title: slot.label ?? slot.sku ?? 'Production', lines }
  }
  if (slot.kind === 'changeover') {
    const lines: string[] = [`Duration: ${duration}`]
    if (slot.changeover_h != null) lines.push(`Changeover: ${slot.changeover_h} h`)
    if (slot.changeover_source)    lines.push(`Source: ${slot.changeover_source.toUpperCase()}`)
    return { title: slot.label ?? 'Changeover', lines }
  }
  return { title: slot.label ?? slot.kind, lines: [`Duration: ${duration}`] }
}

const DAY_LABELS = ['Mon 18', 'Tue 19', 'Wed 20', 'Thu 21', 'Fri 22', 'Sat 23']
const TOTAL_HOURS = 6 * 24

const LEGEND = [
  { label: 'Production',  color: 'bg-[oklch(0.513_0.212_23.4)]' },
  { label: 'Changeover',  color: 'bg-amber-400' },
  { label: 'Cleaning',    color: 'bg-[oklch(0.55_0.1_240)]' },
  { label: 'Maintenance', color: 'bg-[oklch(0.45_0.04_250)]' },
]

interface GanttChartProps {
  sequence: Sequence
  title?: string
}

export function GanttChart({ sequence, title }: GanttChartProps) {
  const [selected, setSelected] = useState<Slot | null>(null)

  const slotsForLine = (line: Line) => sequence.slots.filter(s => s.line === line)

  return (
    <TooltipProvider delayDuration={120}>
      <div className="rounded-xl border bg-card overflow-hidden shadow-sm">
        {/* Title bar */}
        {title && (
          <div className="px-4 py-2.5 border-b bg-muted/20 flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground tracking-wide">{title}</span>
            <span className="text-[10px] text-muted-foreground/60">Click block for details</span>
          </div>
        )}

        {/* Day ruler */}
        <div className="flex border-b bg-muted/10" style={{ paddingLeft: '3.5rem' }}>
          {DAY_LABELS.map((label) => (
            <div
              key={label}
              className="flex-1 text-center text-[10px] font-semibold text-muted-foreground/70 py-1.5 border-l first:border-l-0 border-border/30 tracking-wide"
            >
              {label}
            </div>
          ))}
        </div>

        {/* Line rows */}
        {LINES.map((line, lineIdx) => (
          <div
            key={line}
            className={`flex items-stretch min-h-[3.5rem] ${lineIdx < LINES.length - 1 ? 'border-b border-border/60' : ''}`}
          >
            {/* Line label */}
            <div className="w-14 flex-shrink-0 flex items-center justify-center border-r border-border/60 bg-muted/10">
              <span className="text-[11px] font-bold text-muted-foreground tracking-widest">L{line}</span>
            </div>

            {/* Slots track */}
            <div className="relative flex-1" style={{ height: '3.5rem' }}>
              {/* Day grid lines — very subtle */}
              {[1, 2, 3, 4, 5].map(d => (
                <div
                  key={d}
                  className="absolute inset-y-0 border-l border-border/20"
                  style={{ left: `${(d * 24 / TOTAL_HOURS) * 100}%` }}
                />
              ))}

              {slotsForLine(line).map(slot => {
                const left  = parseHour(slot.start, sequence.week_start)
                const width = parseHour(slot.end,   sequence.week_start) - left
                const leftPct  = (left  / TOTAL_HOURS) * 100
                const widthPct = (width / TOTAL_HOURS) * 100
                const isNarrow = widthPct < 3.5
                const styleClasses = getSlotStyle(slot)
                const { title: tipTitle, lines: tipLines } = formatTooltip(slot)

                return (
                  <Tooltip key={slot.id}>
                    <TooltipTrigger asChild>
                      <button
                        className={[
                          'absolute inset-y-1 rounded-md overflow-hidden',
                          'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
                          'hover:brightness-90 hover:scale-y-105 active:scale-y-100',
                          'transition-all duration-150',
                          styleClasses,
                        ].join(' ')}
                        style={{
                          left:  `calc(${leftPct}% + 1px)`,
                          width: `calc(${widthPct}% - 2px)`,
                        }}
                        onClick={() => setSelected(slot)}
                        aria-label={`${tipTitle} — ${tipLines[0]}`}
                      >
                        {!isNarrow && (
                          <span className="flex items-center h-full px-2 text-[10px] font-semibold leading-none truncate whitespace-nowrap">
                            {slot.kind === 'production'
                              ? (slot.sku?.split('-')[0] ?? slot.label)
                              : slot.label?.split(' ')[0]}
                          </span>
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-[200px]">
                      <p className="font-semibold mb-0.5 text-xs">{tipTitle}</p>
                      {tipLines.map(l => (
                        <p key={l} className="text-[11px] opacity-80">{l}</p>
                      ))}
                    </TooltipContent>
                  </Tooltip>
                )
              })}
            </div>
          </div>
        ))}

        {/* Legend */}
        <div className="flex items-center gap-5 px-4 py-2.5 border-t bg-muted/10 flex-wrap">
          {LEGEND.map(({ label, color }) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className={`h-2.5 w-2.5 rounded-sm ${color}`} />
              <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
      </div>

      <SlotDrawer slot={selected} onClose={() => setSelected(null)} />
    </TooltipProvider>
  )
}
