'use client'

// PlanBuilder — interactive plan input for the plan page.
//
// Two entry flows:
//   CSV    → user uploads a file → client-side parse → products list populated
//   Manual → user types sku_id + quantity_units → products list built by hand
//
// Both converge to the same PlanOptimizeRequest sent to POST /api/plan/optimize.
// That route doesn't exist yet; the call 404s and we fall back to a client-side
// stub that generates a realistic-looking graph from the products. Once the
// backend is wired, no frontend change is needed.
//
// After a successful (or stubbed) run the SequenceGraph + KPI cards + ChatPanel
// appear below the input section.

import { useRef, useState } from 'react'
import { Play, Plus, Trash2, UploadCloud } from 'lucide-react'
import type { PlanOptimizeRequest, PlanOptimizeResponse, PlanProduct } from '@/lib/types/plan-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SequenceGraph } from './sequence-graph'
import { GanttChart } from './gantt-chart'
import { ChatPanel } from './chat-panel'
import { PLACEHOLDER_SOLUTION_ID, chatSeedPlan } from '@/lib/fixtures/chat-messages'
import { optimizePlan, type DataSource } from '@/lib/linewise-api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// CSV parser
// ---------------------------------------------------------------------------

function parseCsv(text: string): PlanProduct[] {
  const lines = text.trim().split(/\r?\n/)
  const header = lines[0].toLowerCase().split(',').map(h => h.trim())

  const skuIdx = header.findIndex(h => h === 'sku_id')
  const qtyIdx = header.findIndex(h => h === 'quantity_units' || h === 'units_produced')

  if (skuIdx === -1 || qtyIdx === -1) return []

  // Aggregate quantities for duplicate SKUs
  const agg: Record<string, number> = {}

  lines.slice(1).forEach(line => {
    const cols = line.split(',')

    const sku = cols[skuIdx]?.trim() ?? ''
    const qty = parseInt(cols[qtyIdx]?.trim() ?? '0', 10)

    if (sku && !isNaN(qty) && qty > 0) {
      agg[sku] = (agg[sku] || 0) + qty
    }
  })

  // Convert aggregated object into Product[]
  return Object.entries(agg).map(([sku_id, quantity_units]) => ({
    sku_id,
    quantity_units,
  }))
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PlanBuilder() {
  const [products, setProducts]   = useState<PlanProduct[]>([])
  const [inputSku, setInputSku]   = useState('')
  const [inputQty, setInputQty]   = useState('')
  const [csvName, setCsvName]     = useState<string | null>(null)
  const [status, setStatus]       = useState<'idle' | 'running' | 'done'>('idle')
  const [result, setResult]       = useState<PlanOptimizeResponse | null>(null)
  const [resultSource, setResultSource] = useState<DataSource | null>(null)
  const fileRef                   = useRef<HTMLInputElement>(null)

  // --- manual add ---
  function addProduct() {
    const sku = inputSku.trim()
    const qty = parseInt(inputQty, 10)
    if (!sku || isNaN(qty) || qty <= 0) return
    setProducts(prev => [...prev, { sku_id: sku, quantity_units: qty }])
    setInputSku('')
    setInputQty('')
  }

  function removeProduct(idx: number) {
    setProducts(prev => prev.filter((_, i) => i !== idx))
  }

  // --- csv upload ---
  function handleFile(file: File) {
    setCsvName(file.name)
    const reader = new FileReader()
    reader.onload = e => {
      const text = e.target?.result as string
      const parsed = parseCsv(text)
      setProducts(parsed)
    }
    reader.readAsText(file)
  }

  // --- run ---
  async function handleRun() {
    if (products.length === 0) return
    setStatus('running')

    const req: PlanOptimizeRequest = { products }
    const response = await optimizePlan(req)
    setResult(response.data)
    setResultSource(response.source)
    setStatus('done')
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-col gap-6">
      {/* Input card */}
      <Card>
        <CardHeader className="border-b py-3">
          <CardTitle className="text-base">Build your weekly plan</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Upload a CSV or add products manually, then run the optimiser.
          </p>
        </CardHeader>
        <CardContent className="pt-4 pb-5">
          <Tabs defaultValue="manual">
            <TabsList className="mb-4">
              <TabsTrigger value="manual">Manual</TabsTrigger>
              <TabsTrigger value="csv">Upload CSV</TabsTrigger>
            </TabsList>

            {/* ---- Manual tab ---- */}
            <TabsContent value="manual">
              <div className="flex flex-wrap items-end gap-3 mb-4">
                <div className="flex-1 min-w-[160px]">
                  <Label className="text-xs mb-1.5 block text-muted-foreground">SKU ID</Label>
                  <Input
                    value={inputSku}
                    onChange={e => setInputSku(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addProduct()}
                    placeholder="e.g. ESTB-1/3-LC"
                    className="h-9 text-sm"
                  />
                </div>
                <div className="w-36">
                  <Label className="text-xs mb-1.5 block text-muted-foreground">Quantity (units)</Label>
                  <Input
                    type="number"
                    min={1}
                    value={inputQty}
                    onChange={e => setInputQty(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addProduct()}
                    placeholder="45 000"
                    className="h-9 text-sm"
                  />
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={addProduct}
                  disabled={!inputSku.trim() || !inputQty}
                  className="h-9"
                >
                  <Plus className="h-3.5 w-3.5 mr-1.5" />
                  Add
                </Button>
              </div>
            </TabsContent>

            {/* ---- CSV tab ---- */}
            <TabsContent value="csv">
              <div
                className="border-2 border-dashed border-border/60 rounded-lg p-8 text-center cursor-pointer hover:border-primary/60 hover:bg-muted/20 transition-colors"
                onClick={() => fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => {
                  e.preventDefault()
                  const file = e.dataTransfer.files[0]
                  if (file) handleFile(file)
                }}
              >
                <UploadCloud className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                {csvName ? (
                  <p className="text-sm font-medium">{csvName}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Drop a CSV here or <span className="text-primary underline-offset-2 underline">click to browse</span>
                  </p>
                )}
                <p className="text-[11px] text-muted-foreground/70 mt-2">
                  Required columns: <code className="font-mono">sku_id</code>, <code className="font-mono">quantity_units</code>
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="sr-only"
                  onChange={e => {
                    const file = e.target.files?.[0]
                    if (file) handleFile(file)
                    e.target.value = ''
                  }}
                />
              </div>
            </TabsContent>
          </Tabs>

          {/* Product list */}
          {products.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground">
                  Products ({products.length})
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-muted-foreground"
                  onClick={() => { setProducts([]); setCsvName(null) }}
                >
                  Clear all
                </Button>
              </div>
              <div className="rounded-lg border divide-y max-h-48 overflow-y-auto">
                {products.map((p, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 text-sm">
                    <span className="font-mono text-xs">{p.sku_id}</span>
                    <div className="flex items-center gap-3">
                      <Badge variant="secondary" className="text-[10px] tabular-nums">
                        {p.quantity_units.toLocaleString()} units
                      </Badge>
                      <button
                        onClick={() => removeProduct(i)}
                        className="text-muted-foreground hover:text-destructive transition-colors"
                        aria-label="Remove product"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Run button */}
          <div className="mt-5 flex justify-end">
            <Button
              onClick={handleRun}
              disabled={products.length === 0 || status === 'running'}
              className="gap-2 min-w-[180px]"
            >
              {status === 'running' ? (
                <>
                  <span className="h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
                  Optimising…
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Run optimisation
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results — only shown after a run */}
      {result && (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Makespan" value={`${result.makespan_h} h`} />
            <StatCard label="Changeovers saved" value={`−${result.h_saved} h`} positive />
            <StatCard label="Coverage" value={`${(result.coverage_pct * 100).toFixed(0)}%`} positive={result.coverage_pct >= 1} />
            <StatCard
              label="Dropped SKUs"
              value={result.dropped_skus.length === 0 ? 'None' : String(result.dropped_skus.length)}
              positive={result.dropped_skus.length === 0}
            />
          </div>

          <div className="flex justify-end">
            <Badge variant={resultSource === 'backend' ? 'default' : 'outline'}>
              {resultSource === 'backend' ? 'Backend optimizer' : 'Mock optimizer fallback'}
            </Badge>
          </div>

          <SequenceGraph
            nodes={result.nodes}
            edges={result.edges}
            stats={{
              makespan_h: result.makespan_h,
              h_saved: result.h_saved,
              coverage_pct: result.coverage_pct,
            }}
            title="Sequence graph — LineWise proposal"
          />

          <GanttChart
            sequence={result.sequence}
            title="Resulting schedule — LineWise proposal"
          />

          <ChatPanel
            solutionId={PLACEHOLDER_SOLUTION_ID}
            scope={{ view: 'plan' }}
            seedMessages={chatSeedPlan}
          />
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 px-4">
        <p className="text-xs text-muted-foreground font-medium mb-1">{label}</p>
        <p className={`text-2xl font-bold tabular-nums tracking-tight ${positive ? 'text-emerald-600' : ''}`}>
          {value}
        </p>
      </CardContent>
    </Card>
  )
}
