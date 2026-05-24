import { PLACEHOLDER_SOLUTION_ID, chatSeedWhatIf } from '@/lib/fixtures'
import { ChatPanel } from '@/components/linewise/chat-panel'
import { WhatIfForm } from '@/components/linewise/whatif-form'

export default function WhatIfPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">What-If</h1>
        <p className="text-muted-foreground mt-1">
          Inject a perturbation — LineWise re-plans the week and recommends the optimal line assignment.
        </p>
      </div>

      <WhatIfForm />

      <ChatPanel
        solutionId={PLACEHOLDER_SOLUTION_ID}
        scope={{ view: 'what-if' }}
        seedMessages={chatSeedWhatIf}
      />
    </div>
  )
}
