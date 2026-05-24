import { PlanBuilder } from '@/components/linewise/plan-builder'

export default function PlanPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Production Plan</h1>
        <p className="text-muted-foreground mt-1">
          Add your weekly products and let LineWise find the shortest sequence across L14, L17 and L19.
        </p>
      </div>

      <PlanBuilder />
    </div>
  )
}
