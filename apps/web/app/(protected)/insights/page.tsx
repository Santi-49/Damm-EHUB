export default function InsightsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Insights</h1>
        <p className="text-muted-foreground">Historical inefficiencies, worst transitions and OEE loss breakdown.</p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center">
        <p className="text-muted-foreground">Inefficiency table + heatmap coming in Phase 4</p>
      </div>
    </div>
  )
}
