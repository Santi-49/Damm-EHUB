import type { DroppedSku } from '@/lib/types/linewise'
import { AlertTriangle } from 'lucide-react'

interface DroppedSkuPanelProps {
  skus: DroppedSku[]
}

export function DroppedSkuPanel({ skus }: DroppedSkuPanelProps) {
  if (skus.length === 0) return null

  const totalLost = skus.reduce((s, d) => s + d.margin_lost, 0)

  return (
    <div className="rounded-xl border border-red-200 bg-red-50 overflow-hidden">
      <div className="px-4 py-3 border-b border-red-200 flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-red-600" />
        <span className="text-sm font-medium text-red-800">
          Dropped SKUs in S_real — €{totalLost.toLocaleString()} margin at risk
        </span>
      </div>
      <div className="divide-y divide-red-100">
        {skus.map(d => (
          <div key={d.sku} className="px-4 py-3 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm font-mono font-medium text-red-900">{d.sku}</p>
              <p className="text-xs text-red-700 mt-0.5">{d.reason}</p>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="text-sm font-bold tabular-nums text-red-800">€{d.margin_lost.toLocaleString()}</p>
              <p className="text-xs text-red-600">{d.units_dropped.toLocaleString()} units</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
