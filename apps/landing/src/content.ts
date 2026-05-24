export const landingContent = {
  productName: "Quick2Plan",
  appUrl: "http://localhost:5173",
  nav: [
    { label: "Why Quick2Plan", href: "#why" },
    { label: "AI Stack", href: "#features" },
    { label: "Demo", href: "#demo" },
  ],
  headline: "Quick2Plan finds the optimal canning sequence in seconds.",
  subheadline:
    "We revolutionize industrial production planning by turning weekly demand, line restrictions, changeover costs, and disruptions into fast, explainable, user-friendly plans for L14, L17, and L19.",
  primaryCta: "Open planning demo",
  secondaryCta: "See how it works",
  heroStats: [
    {
      value: "73.5h",
      label: "productive routing hours saved per week in the clean historical replay",
    },
    {
      value: "53/53",
      label: "weekly 2025 windows won by the v2 optimizer",
    },
    {
      value: "<5s",
      label: "target re-plan latency when a breakdown or urgent order hits",
    },
  ],
  whyTitle: "Revolutionizing planning in every dimension.",
  whySubtitle:
    "Quick2Plan is not another dashboard. It is a planning engine, a simulation layer, and an AI assistant working together so planners can move from demand to a defensible sequence without spreadsheet guesswork.",
  cards: [
    {
      title: "Optimal by design",
      text: "Every SKU chunk becomes a graph node and every transition becomes a weighted edge, so the system searches for the shortest weekly path across the three canning lines.",
      metricLabel: "Objective",
      metric: "Min makespan",
    },
    {
      title: "Fast under pressure",
      text: "What-if replanning reacts to breakdowns, urgent demand, and capacity shortfalls while keeping hard line-format constraints intact.",
      metricLabel: "Re-plan",
      metric: "<5s",
    },
    {
      title: "Built for planners",
      text: "The app shows a Gantt by line, side-by-side comparisons, dropped SKUs, and transition drill-downs so the recommendation is easy to inspect.",
      metricLabel: "Workflow",
      metric: "One click",
    },
    {
      title: "Explainable with chat",
      text: "A grounded assistant answers why a SKU moved, what made a changeover expensive, and how the optimized plan differs from the real week.",
      metricLabel: "Trace",
      metric: "Reasoned",
    },
  ],
  featuresTitle: "AI that plans, predicts, clusters, and explains.",
  featuresSubtitle:
    "The engine combines graph optimization, CatBoost production-time prediction, K-means SKU segmentation, deterministic OEE simulation, and a chatbot explanation layer.",
  featurePanels: [
    {
      title: "Graph optimization core",
      text: "Architecture D models the week as a multi-vehicle routing problem: L14, L17, and L19 split demand while minimizing the bottleneck line.",
    },
    {
      title: "Scenario re-planning",
      text: "Breakdowns and urgent orders become new constraints, not manual firefighting. Frozen slots stay fixed and the remaining week is rebuilt.",
    },
    {
      title: "CatBoost intelligence",
      text: "CatBoost predicts effective production speed from SKU, line, units, and historical run context, giving the graph realistic node costs.",
    },
    {
      title: "K-means segmentation",
      text: "SKU families are clustered to reveal operational patterns and make changeover behavior easier to see, audit, and communicate.",
    },
    {
      title: "Fair OEE simulation",
      text: "The simulator replays the same incidents and calendar constraints on real and optimized sequences, so comparisons are measurable and fair.",
    },
  ],
  demoTitle: "Ready for the hackathon demo. Built like a plant-floor product.",
  demoSubtitle:
    "Run the weekly plan, compare real vs optimized, inject a disruption, then ask the assistant why the sequence changed.",
};
