'use client'

import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { ImpactHero } from '@/components/linewise/impact-hero'
import { ImpactHeatmap } from '@/components/linewise/impact-heatmap'
import { ImpactRankedList } from '@/components/linewise/impact-ranked-list'
import { getImpactAtlas, type ApiResult } from '@/lib/linewise-api'
import { impactAtlas2025 } from '@/lib/fixtures/impact-atlas'
import type { ImpactAtlas } from '@/lib/types/insights'

export default function InsightsPage() {
  const [result, setResult] = useState<ApiResult<ImpactAtlas>>({
    data: impactAtlas2025,
    source: 'mock',
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    getImpactAtlas(2025).then(r => {
      if (!active) return
      setResult(r)
      setLoading(false)
    })
    return () => { active = false }
  }, [])

  const atlas = result.data

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl font-bold tracking-tight">2025 Impact Atlas</h1>
            <Badge variant="secondary">Counterfactual replay</Badge>
          </div>
          <p className="text-muted-foreground mt-1">
            Every production week of 2025 replayed through the LineWise optimiser — same demand window, same incidents, fair fight.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Backend endpoint: <code className="font-mono">GET /api/v1/linewise/impact-atlas?year=2025</code>. Falls back to a deterministic fixture until the engine ships.
          </p>
        </div>
        <Badge variant={result.source === 'backend' ? 'default' : 'outline'}>
          {loading ? 'Loading' : result.source === 'backend' ? 'Backend result' : 'Mock fallback'}
        </Badge>
      </div>

      <ImpactHero atlas={atlas} />

      <ImpactHeatmap atlas={atlas} />

      <ImpactRankedList atlas={atlas} limit={10} />
    </div>
  )
}
