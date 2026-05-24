import type { SimulationReport } from '@/lib/types/linewise'

export const simulationOpt: SimulationReport = {
  sequence_id: 'seq-opt-2026-w20',
  oee_global: 0.824,
  h_changes: 16.0,
  h_productive: 287.5,
  coverage: 0.98,
  makespan_h: 136.0,
  oee_per_line: [
    { line: 14, oee: 0.831, h_productive: 98.0,  h_changeover: 7.5,  h_cleaning: 2.0, h_maintenance: 8.0, h_idle: 0.0, coverage: 1.0  },
    { line: 17, oee: 0.818, h_productive: 97.0,  h_changeover: 4.5,  h_cleaning: 2.0, h_maintenance: 0.0, h_idle: 0.0, coverage: 1.0  },
    { line: 19, oee: 0.823, h_productive: 92.5,  h_changeover: 4.0,  h_cleaning: 2.0, h_maintenance: 0.0, h_idle: 0.0, coverage: 0.94 },
  ],
  dropped_skus: [],
}

export const simulationReal: SimulationReport = {
  sequence_id: 'seq-real-2026-w20',
  oee_global: 0.786,
  h_changes: 24.5,
  h_productive: 274.0,
  coverage: 0.93,
  makespan_h: 136.0,
  oee_per_line: [
    { line: 14, oee: 0.788, h_productive: 92.5,  h_changeover: 13.0, h_cleaning: 2.5, h_maintenance: 8.0, h_idle: 0.0, coverage: 0.96 },
    { line: 17, oee: 0.786, h_productive: 91.0,  h_changeover:  8.5, h_cleaning: 2.5, h_maintenance: 0.0, h_idle: 0.0, coverage: 0.94 },
    { line: 19, oee: 0.784, h_productive: 90.5,  h_changeover:  3.0, h_cleaning: 2.0, h_maintenance: 0.0, h_idle: 0.0, coverage: 0.89 },
  ],
  dropped_skus: [
    { sku: 'FREQ-2/5-25', units_demanded: 6000,  units_dropped: 6000,  margin_lost: 1260, reason: 'Capacity lost due to format changeover overruns on L19' },
    { sku: 'DAMM-1/3-33', units_demanded: 4000,  units_dropped: 4000,  margin_lost: 720,  reason: 'Monday cleaning overrun cascaded into late production start' },
  ],
}
