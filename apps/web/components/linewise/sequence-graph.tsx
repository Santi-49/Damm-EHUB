'use client'

// Sequence graph — renders an optimiser result as a node-edge diagram.
//
// Two edge layers are drawn over the same node set:
//   solid coloured = baseline (S_real / JDA order); width + colour encode cost
//   dashed purple  = LineWise proposed path (S_opt)
//
// Node positions are computed automatically from line_id (line 14 top,
// 17 middle, 19 bottom). Node size scales with production volume.

import { useMemo } from 'react'
import {
  Background,
  Controls,
  type Edge,
  MarkerType,
  MiniMap,
  type Node,
  ReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { PlanGraphEdge, PlanGraphNode } from '@/lib/types/plan-api'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const FAMILY_BG: Record<string, string> = {
  DAMM:  'oklch(0.513 0.212 23.4)',
  ESTB:  'oklch(0.46 0.18 23.4)',
  DAURA: 'oklch(0.55 0.16 28)',
  LEMO:  'oklch(0.60 0.13 85)',
  FREQ:  'oklch(0.55 0.13 145)',
  RDSQ:  'oklch(0.44 0.15 340)',
  VOLL:  'oklch(0.38 0.17 23.4)',
}

const OPT_COLOR = '#7F77DD'

function edgeColor(hours: number): string {
  if (hours > 1.5) return '#E24B4A'
  if (hours > 0.8) return '#EF9F27'
  return '#1D9E75'
}

// Fixed spacing so nodes never overlap, even with 50+ SKUs on one line.
// The canvas grows as wide as it needs to — React Flow handles pan/zoom and
// the minimap gives orientation when zoomed in.
const NODE_SPACING_X = 140
const LINE_Y: Record<number, number> = { 14: 60, 17: 200, 19: 340 }

function computeLayout(nodes: PlanGraphNode[]): Map<string, { x: number; y: number }> {
  const byLine: Record<number, PlanGraphNode[]> = { 14: [], 17: [], 19: [] }
  nodes.forEach(n => byLine[n.line_id]?.push(n))

  const positions = new Map<string, { x: number; y: number }>()
  Object.entries(byLine).forEach(([line, lineNodes]) => {
    lineNodes.forEach((n, i) => {
      positions.set(n.id, {
        x: 80 + i * NODE_SPACING_X,
        y: LINE_Y[Number(line)] ?? 200,
      })
    })
  })

  return positions
}

interface SequenceStats {
  makespan_h: number
  h_saved: number
  coverage_pct: number
}

export interface SequenceGraphProps {
  nodes: PlanGraphNode[]
  edges: PlanGraphEdge[]
  stats?: SequenceStats
  title?: string
}

export function SequenceGraph({ nodes, edges, stats, title = 'Sequence graph' }: SequenceGraphProps) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const positions = computeLayout(nodes)

    const rfNodes: Node[] = nodes.map(n => {
      const pos = positions.get(n.id) ?? { x: 0, y: 0 }
      const size = 56 + Math.min(40, n.volume_hl / 14)
      return {
        id: n.id,
        position: pos,
        data: { label: n.label },
        draggable: false,
        connectable: false,
        selectable: false,
        style: {
          width: size,
          height: size,
          borderRadius: '50%',
          background: FAMILY_BG[n.family] ?? 'oklch(0.5 0.05 250)',
          color: '#fff',
          border: 'none',
          fontSize: 10,
          fontWeight: 500,
          textAlign: 'center',
          padding: 4,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          lineHeight: 1.2,
        } as React.CSSProperties,
      }
    })

    const rfEdges: Edge[] = edges.map(e => {
      const isOpt = e.path === 'opt'
      const colour = isOpt ? OPT_COLOR : edgeColor(e.hours)
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: `${e.hours}h`,
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
        labelStyle: { fontSize: 10, fontWeight: 600, fill: colour },
        labelBgStyle: { fill: 'var(--background)', opacity: 0.9 },
        style: {
          stroke: colour,
          strokeWidth: isOpt ? 2.5 : Math.max(1.5, e.hours * 1.5),
          strokeDasharray: isOpt ? '6 4' : undefined,
          opacity: 0.85,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: colour },
      }
    })

    return { rfNodes, rfEdges }
  }, [nodes, edges])

  // Pairs where both 'baseline' and 'opt' edges exist — used for "avoided" card
  const avoidedPairs = useMemo(() => {
    const optMap = new Map(edges.filter(e => e.path === 'opt').map(e => [`${e.source}→${e.target}`, e]))
    return edges
      .filter(e => e.path === 'baseline')
      .map(e => {
        const opt = optMap.get(`${e.source}→${e.target}`)
        if (!opt || opt.hours >= e.hours) return null
        return { pair: `${e.source} → ${e.target}`, saved: +(e.hours - opt.hours).toFixed(1), baseline: e.hours, opt: opt.hours }
      })
      .filter(Boolean)
      .sort((a, b) => b!.saved - a!.saved)
      .slice(0, 3) as Array<{ pair: string; saved: number; baseline: number; opt: number }>
  }, [edges])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-3">
      <Card className="overflow-hidden">
        <CardHeader className="border-b py-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-base">{title}</CardTitle>
            <div className="flex gap-2 flex-wrap">
              <Badge variant="destructive" className="text-[10px]">Baseline</Badge>
              <Badge className="text-[10px] bg-violet-500 hover:bg-violet-500">LineWise (dashed)</Badge>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Node size = production volume · Edge width &amp; colour = changeover cost · Dashed purple = proposed path
          </p>
        </CardHeader>
        <CardContent className="p-0">
          <div style={{ height: 520 }} className="bg-muted/10 relative">
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              proOptions={{ hideAttribution: true }}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              panOnDrag
              zoomOnScroll
              minZoom={0.15}
              maxZoom={1.8}
            >
              <Background gap={20} size={1} />
              <Controls showInteractive={false} className="shadow-sm! border!" />
              <MiniMap
                pannable
                zoomable
                nodeColor={(node) => {
                  const family = nodes.find(n => n.id === node.id)?.family ?? ''
                  return FAMILY_BG[family] ?? 'oklch(0.5 0.05 250)'
                }}
                maskColor="oklch(0.96 0 0 / 0.7)"
                className="border! shadow-sm!"
              />
            </ReactFlow>
          </div>
          <div className="px-4 py-2 border-t bg-muted/20 text-[10px] text-muted-foreground flex items-center justify-between flex-wrap gap-2">
            <span>Drag to pan · scroll to zoom · use the minimap or controls bottom-left</span>
            <span className="tabular-nums">L14 top · L17 middle · L19 bottom</span>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3">
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Result</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pb-4">
            {stats ? (
              <>
                <div>
                  <div className="text-2xl font-semibold text-foreground tabular-nums">
                    {stats.makespan_h} h
                  </div>
                  <div className="text-[11px] text-muted-foreground">makespan (slowest line)</div>
                </div>
                <div className="rounded-md bg-emerald-500/10 border border-emerald-500/30 px-3 py-2">
                  <div className="text-sm font-semibold text-emerald-600">
                    −{stats.h_saved} h changeovers
                  </div>
                  <div className="text-[11px] text-emerald-600/80">
                    vs baseline ordering
                  </div>
                </div>
                <div className="text-sm tabular-nums text-muted-foreground">
                  Coverage{' '}
                  <span className={stats.coverage_pct >= 1 ? 'text-emerald-600 font-semibold' : 'text-amber-600 font-semibold'}>
                    {(stats.coverage_pct * 100).toFixed(0)}%
                  </span>
                </div>
              </>
            ) : (
              <div className="text-[11px] text-muted-foreground">Run to see results</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Avoided transitions</CardTitle>
          </CardHeader>
          <CardContent className="pb-4 text-[11px] text-muted-foreground leading-relaxed">
            {avoidedPairs.length > 0 ? (
              <>
                Re-ordering removes <strong className="text-red-500">{avoidedPairs.length} expensive edge{avoidedPairs.length > 1 ? 's' : ''}</strong>:
                <ul className="mt-1.5 space-y-0.5">
                  {avoidedPairs.map(p => (
                    <li key={p.pair}>· {p.pair} ({p.baseline}h → {p.opt}h)</li>
                  ))}
                </ul>
                <div className="mt-1.5">
                  Total saved:{' '}
                  <strong className="text-emerald-600">
                    {avoidedPairs.reduce((s, p) => +(s + p.saved).toFixed(1), 0)} h
                  </strong>
                </div>
              </>
            ) : (
              <span>No comparable pairs yet</span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Why this order?</CardTitle>
          </CardHeader>
          <CardContent className="pb-4 text-[11px] text-muted-foreground leading-relaxed">
            Group same-content SKUs to skip flavour changes, place reference changes at shift boundaries, and keep same-format runs consecutive.
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
