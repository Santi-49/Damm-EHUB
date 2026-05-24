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
            <h1 className="text-3xl font-bold tracking-tight">Optimizer v2 Impact</h1>
            <Badge variant="secondary">2025 replay benchmark</Badge>
          </div>
          <p className="text-muted-foreground mt-1">
            The 53-window benchmark replayed through LineWise v2 — clean routing savings, adjusted stress tests, and weekly drill-down.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Source: <code className="font-mono">{atlas.source_dataset}</code>. The web fixture is hardcoded from the latest report.
          </p>
        </div>
        <Badge variant={result.source === 'backend' ? 'default' : 'outline'}>
          {loading ? 'Loading' : result.source === 'backend' ? 'Backend result' : 'Hardcoded benchmark'}
        </Badge>
      </div>

      <ImpactHero atlas={atlas} />

      <ImpactHeatmap atlas={atlas} />

      <ImpactRankedList atlas={atlas} limit={10} />
    </div>
  )
}
