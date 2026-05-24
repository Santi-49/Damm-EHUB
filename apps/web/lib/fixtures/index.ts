export { sequenceOpt } from './sequence-opt'
export { sequenceReal } from './sequence-real'
export { simulationOpt, simulationReal } from './simulation-reports'
export { inefficiencies } from './inefficiencies'
export { skuMaster } from './sku-master'
export {
  PLACEHOLDER_SOLUTION_ID,
  chatSeedCompare,
  chatSeedPlan,
  chatSeedWhatIf,
} from './chat-messages'
export { sequenceGraphLine17 } from './sequence-graph'
export { dailyOee } from './oee-overlay'

import { simulationOpt, simulationReal } from './simulation-reports'
import type { DeltaMetrics } from '@/lib/types/linewise'

export function computeDelta(): DeltaMetrics {
  return {
    oee_pp:               +(simulationOpt.oee_global - simulationReal.oee_global).toFixed(3),
    h_changes_saved:      +(simulationReal.h_changes - simulationOpt.h_changes).toFixed(1),
    h_productive_gained:  +(simulationOpt.h_productive - simulationReal.h_productive).toFixed(1),
    coverage_delta:       +(simulationOpt.coverage - simulationReal.coverage).toFixed(3),
  }
}
