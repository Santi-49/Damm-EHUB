// Placeholder daily OEE — used by the post-mortem overlay on the compare page.
// Each row: one day of the planning week with planned vs actual OEE [0–1].

export interface DayOee {
  day: string
  short: string
  oee_actual: number
  oee_planned: number
}

export const dailyOee: DayOee[] = [
  { day: 'Monday',    short: 'Mon', oee_actual: 0.71, oee_planned: 0.74 },
  { day: 'Tuesday',   short: 'Tue', oee_actual: 0.43, oee_planned: 0.69 },
  { day: 'Wednesday', short: 'Wed', oee_actual: 0.55, oee_planned: 0.68 },
  { day: 'Thursday',  short: 'Thu', oee_actual: 0.22, oee_planned: 0.65 },
  { day: 'Friday',    short: 'Fri', oee_actual: 0.63, oee_planned: 0.67 },
  { day: 'Saturday',  short: 'Sat', oee_actual: 0.68, oee_planned: 0.70 },
  { day: 'Sunday',    short: 'Sun', oee_actual: 0.38, oee_planned: 0.62 },
]
