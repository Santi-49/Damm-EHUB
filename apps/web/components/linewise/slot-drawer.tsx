'use client'

import type { Slot } from '@/lib/types/linewise'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

interface SlotDrawerProps {
  slot: Slot | null
  onClose: () => void
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function formatDuration(start: string, end: string): string {
  const h = (new Date(end).getTime() - new Date(start).getTime()) / (1000 * 60 * 60)
  return `${h.toFixed(2)} h`
}

const KIND_BADGE: Record<string, string> = {
  production:  'bg-primary/10 text-primary border-primary/20',
  changeover:  'bg-amber-100 text-amber-800 border-amber-200',
  cleaning:    'bg-blue-100 text-blue-800 border-blue-200',
  maintenance: 'bg-emerald-100 text-emerald-800 border-emerald-200',
}

export function SlotDrawer({ slot, onClose }: SlotDrawerProps) {
  const oeeGap = slot?.oee_expected != null && slot?.oee_actual != null
    ? slot.oee_actual - slot.oee_expected
    : null

  return (
    <Sheet open={slot !== null} onOpenChange={open => { if (!open) onClose() }}>
      <SheetContent className="w-80 sm:w-96 overflow-y-auto">
        {slot && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="outline" className={KIND_BADGE[slot.kind] ?? ''}>
                  {slot.kind}
                </Badge>
                <span className="text-xs text-muted-foreground">Line {slot.line}</span>
              </div>
              <SheetTitle className="leading-snug">
                {slot.label ?? slot.sku ?? slot.kind}
              </SheetTitle>
            </SheetHeader>

            <div className="mt-4 space-y-4">
              {/* Timing */}
              <Section title="Timing">
                <Row label="Start"    value={formatTime(slot.start)} />
                <Row label="End"      value={formatTime(slot.end)} />
                <Row label="Duration" value={formatDuration(slot.start, slot.end)} />
              </Section>

              {/* Production details */}
              {slot.kind === 'production' && (
                <Section title="Production">
                  {slot.sku    && <Row label="SKU"   value={slot.sku} mono />}
                  {slot.units  && <Row label="Units" value={slot.units.toLocaleString()} />}
                  {slot.oee_expected != null && (
                    <Row label="OEE expected" value={`${(slot.oee_expected * 100).toFixed(1)}%`} />
                  )}
                  {slot.oee_actual != null && (
                    <Row
                      label="OEE actual"
                      value={`${(slot.oee_actual * 100).toFixed(1)}%`}
                      highlight={oeeGap != null && oeeGap < -0.02 ? 'warn' : undefined}
                    />
                  )}
                  {oeeGap != null && (
                    <Row
                      label="OEE gap"
                      value={`${oeeGap >= 0 ? '+' : ''}${(oeeGap * 100).toFixed(1)} pp`}
                      highlight={oeeGap < -0.02 ? 'warn' : 'ok'}
                    />
                  )}
                </Section>
              )}

              {/* Changeover details */}
              {slot.kind === 'changeover' && (
                <Section title="Changeover">
                  {slot.sku && <Row label="From SKU" value={slot.sku} mono />}
                  {slot.changeover_h != null && (
                    <Row label="Actual time" value={`${slot.changeover_h} h`} />
                  )}
                  {slot.changeover_source && (
                    <Row label="Estimate source" value={slot.changeover_source.toUpperCase()} />
                  )}
                  {slot.changeover_drivers && slot.changeover_drivers.length > 0 && (
                    <>
                      <Separator className="my-2" />
                      <p className="text-xs font-medium text-muted-foreground mb-2">Cost drivers</p>
                      {slot.changeover_drivers.map(d => (
                        <div key={d.feature} className="flex justify-between items-center text-xs mb-1">
                          <span className="text-foreground/70 font-mono">{d.feature}</span>
                          <span className={`font-medium tabular-nums ${d.impact_h > 0 ? 'text-amber-700' : 'text-emerald-700'}`}>
                            {d.impact_h > 0 ? '+' : ''}{d.impact_h} h
                          </span>
                        </div>
                      ))}
                    </>
                  )}
                </Section>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{title}</p>
      <div className="rounded-lg border bg-muted/20 px-3 py-2 space-y-1.5">
        {children}
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  mono,
  highlight,
}: {
  label: string
  value: string
  mono?: boolean
  highlight?: 'warn' | 'ok'
}) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={[
          mono ? 'font-mono' : 'font-medium',
          highlight === 'warn' ? 'text-amber-700' : '',
          highlight === 'ok'   ? 'text-emerald-700' : '',
        ].join(' ')}
      >
        {value}
      </span>
    </div>
  )
}
