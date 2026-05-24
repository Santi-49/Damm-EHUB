import type { ImpactAtlas, WeekImpact } from '@/lib/types/insights'

type ActualWeekReplay = {
  id: string
  nodes: number
  v2: number
  real: number
  clean: number
  adjusted: number
  maintenance: number
  mixed: number
  cleaning: number
  maintLoad: number
}

// Hardcoded from services/optimizer/reports/optimizer_v2_makespan_comparison.csv.
// The headline values match services/optimizer/reports/optimizer_v2_brief_conclusions.md.
const ACTUAL_WEEK_REPLAY: ActualWeekReplay[] = [
  { id: '2025-W01-7d', nodes: 7, v2: 21.5, real: 40.7, clean: 19.2, adjusted: -9.6, maintenance: -9.6, mixed: -15.5, cleaning: 13.8, maintLoad: 24.0 },
  { id: '2025-W02-7d', nodes: 33, v2: 57.2, real: 102.5, clean: 45.3, adjusted: -3.4, maintenance: -2.4, mixed: -9.2, cleaning: 15.1, maintLoad: 11.0 },
  { id: '2025-W03-7d', nodes: 26, v2: 64.5, real: 117.8, clean: 53.2, adjusted: 5.3, maintenance: -2.1, mixed: -2.5, cleaning: 14.6, maintLoad: 13.3 },
  { id: '2025-W04-7d', nodes: 42, v2: 77.8, real: 130.3, clean: 52.5, adjusted: 10.2, maintenance: 1.3, mixed: 6.6, cleaning: 9.2, maintLoad: 39.0 },
  { id: '2025-W05-7d', nodes: 35, v2: 74.1, real: 135.8, clean: 61.7, adjusted: 18.2, maintenance: 3.1, mixed: 7.2, cleaning: 3.3, maintLoad: 33.0 },
  { id: '2025-W06-7d', nodes: 38, v2: 90.4, real: 143.0, clean: 52.7, adjusted: 6.2, maintenance: 12.5, mixed: 4.4, cleaning: 14.1, maintLoad: 51.3 },
  { id: '2025-W07-7d', nodes: 26, v2: 64.5, real: 134.6, clean: 70.2, adjusted: 37.3, maintenance: -19.4, mixed: 30.4, cleaning: 10.7, maintLoad: 160.9 },
  { id: '2025-W08-7d', nodes: 35, v2: 105.6, real: 161.6, clean: 56.0, adjusted: 5.9, maintenance: 5.9, mixed: -15.9, cleaning: 20.6, maintLoad: 15.1 },
  { id: '2025-W09-7d', nodes: 31, v2: 50.4, real: 105.9, clean: 55.5, adjusted: 18.7, maintenance: -19.6, mixed: 11.9, cleaning: 13.0, maintLoad: 199.1 },
  { id: '2025-W10-7d', nodes: 38, v2: 112.7, real: 143.7, clean: 31.0, adjusted: -18.2, maintenance: -18.2, mixed: -31.1, cleaning: 13.8, maintLoad: 37.5 },
  { id: '2025-W11-7d', nodes: 33, v2: 74.1, real: 143.0, clean: 68.9, adjusted: 28.7, maintenance: 24.5, mixed: 27.0, cleaning: 9.6, maintLoad: 12.0 },
  { id: '2025-W12-7d', nodes: 30, v2: 69.5, real: 135.9, clean: 66.3, adjusted: 22.8, maintenance: 22.8, mixed: 16.6, cleaning: 12.2, maintLoad: 36.5 },
  { id: '2025-W13-7d', nodes: 32, v2: 97.9, real: 177.5, clean: 79.6, adjusted: 19.7, maintenance: 19.7, mixed: 14.2, cleaning: 4.2, maintLoad: 33.6 },
  { id: '2025-W14-7d', nodes: 45, v2: 98.0, real: 175.4, clean: 77.5, adjusted: -6.1, maintenance: -6.1, mixed: -3.3, cleaning: 9.3, maintLoad: 8.4 },
  { id: '2025-W15-7d', nodes: 34, v2: 91.7, real: 155.8, clean: 64.1, adjusted: 5.5, maintenance: 5.5, mixed: 0.3, cleaning: 10.8, maintLoad: 0.0 },
  { id: '2025-W16-7d', nodes: 38, v2: 107.0, real: 158.0, clean: 51.0, adjusted: 3.6, maintenance: 3.6, mixed: -2.2, cleaning: 6.4, maintLoad: 4.3 },
  { id: '2025-W17-7d', nodes: 29, v2: 100.5, real: 168.7, clean: 68.2, adjusted: 18.7, maintenance: -11.3, mixed: 19.3, cleaning: 17.4, maintLoad: 82.4 },
  { id: '2025-W18-7d', nodes: 23, v2: 43.2, real: 112.1, clean: 68.8, adjusted: 22.4, maintenance: 22.4, mixed: 13.8, cleaning: 18.1, maintLoad: 97.8 },
  { id: '2025-W19-7d', nodes: 34, v2: 114.7, real: 239.2, clean: 124.4, adjusted: 32.6, maintenance: 32.6, mixed: 25.9, cleaning: 26.5, maintLoad: 17.0 },
  { id: '2025-W20-7d', nodes: 38, v2: 108.7, real: 174.9, clean: 66.1, adjusted: 8.7, maintenance: 15.7, mixed: 6.1, cleaning: 16.2, maintLoad: 44.6 },
  { id: '2025-W21-7d', nodes: 28, v2: 55.5, real: 164.5, clean: 109.1, adjusted: 65.5, maintenance: 48.7, mixed: 58.9, cleaning: 8.5, maintLoad: 109.7 },
  { id: '2025-W22-7d', nodes: 24, v2: 43.9, real: 115.2, clean: 71.3, adjusted: 39.5, maintenance: 12.7, mixed: 28.9, cleaning: 14.7, maintLoad: 180.3 },
  { id: '2025-W23-7d', nodes: 37, v2: 102.0, real: 163.4, clean: 61.3, adjusted: 16.3, maintenance: 40.2, mixed: 3.3, cleaning: 16.3, maintLoad: 88.7 },
  { id: '2025-W24-7d', nodes: 40, v2: 109.6, real: 192.7, clean: 83.1, adjusted: 21.8, maintenance: 31.1, mixed: 14.7, cleaning: 6.0, maintLoad: 33.5 },
  { id: '2025-W25-7d', nodes: 42, v2: 114.1, real: 185.6, clean: 71.5, adjusted: 14.9, maintenance: 13.2, mixed: 10.6, cleaning: 22.8, maintLoad: 20.9 },
  { id: '2025-W26-7d', nodes: 37, v2: 90.1, real: 189.9, clean: 99.8, adjusted: 18.9, maintenance: 18.9, mixed: 7.7, cleaning: 23.7, maintLoad: 8.3 },
  { id: '2025-W27-7d', nodes: 30, v2: 100.4, real: 171.4, clean: 71.0, adjusted: 26.7, maintenance: 7.1, mixed: 23.3, cleaning: 15.4, maintLoad: 40.2 },
  { id: '2025-W28-7d', nodes: 42, v2: 139.1, real: 295.6, clean: 156.5, adjusted: 82.9, maintenance: 65.3, mixed: 81.1, cleaning: 3.6, maintLoad: 34.7 },
  { id: '2025-W29-7d', nodes: 34, v2: 90.5, real: 156.8, clean: 66.4, adjusted: 5.5, maintenance: 14.7, mixed: 1.7, cleaning: 6.3, maintLoad: 52.8 },
  { id: '2025-W30-7d', nodes: 45, v2: 100.1, real: 193.1, clean: 93.0, adjusted: 23.1, maintenance: -15.8, mixed: 18.9, cleaning: 9.2, maintLoad: 105.4 },
  { id: '2025-W31-7d', nodes: 37, v2: 87.0, real: 151.9, clean: 64.9, adjusted: 19.2, maintenance: 18.0, mixed: 14.1, cleaning: 20.8, maintLoad: 60.9 },
  { id: '2025-W32-7d', nodes: 39, v2: 105.6, real: 214.6, clean: 109.0, adjusted: 39.9, maintenance: 31.7, mixed: 35.6, cleaning: 26.7, maintLoad: 21.1 },
  { id: '2025-W33-7d', nodes: 38, v2: 96.0, real: 206.7, clean: 110.6, adjusted: 50.5, maintenance: -19.2, mixed: 54.6, cleaning: 13.6, maintLoad: 117.2 },
  { id: '2025-W34-7d', nodes: 35, v2: 102.5, real: 171.7, clean: 69.2, adjusted: 25.5, maintenance: -5.8, mixed: 20.8, cleaning: 22.0, maintLoad: 33.2 },
  { id: '2025-W35-7d', nodes: 35, v2: 129.7, real: 238.5, clean: 108.9, adjusted: 40.6, maintenance: 40.6, mixed: 36.9, cleaning: 21.6, maintLoad: 0.0 },
  { id: '2025-W36-7d', nodes: 31, v2: 106.1, real: 175.7, clean: 69.6, adjusted: 19.5, maintenance: 10.0, mixed: 17.2, cleaning: 25.5, maintLoad: 39.8 },
  { id: '2025-W37-7d', nodes: 31, v2: 92.9, real: 147.9, clean: 55.0, adjusted: 2.1, maintenance: -10.6, mixed: -3.4, cleaning: 21.4, maintLoad: 40.4 },
  { id: '2025-W38-7d', nodes: 35, v2: 123.0, real: 242.6, clean: 119.6, adjusted: 38.4, maintenance: 38.4, mixed: 38.2, cleaning: 15.9, maintLoad: 27.9 },
  { id: '2025-W39-7d', nodes: 27, v2: 118.1, real: 229.4, clean: 111.3, adjusted: 24.8, maintenance: 22.9, mixed: 16.0, cleaning: 18.3, maintLoad: 59.8 },
  { id: '2025-W40-7d', nodes: 29, v2: 98.4, real: 187.0, clean: 88.6, adjusted: 54.6, maintenance: -0.3, mixed: 46.9, cleaning: 13.0, maintLoad: 54.9 },
  { id: '2025-W41-7d', nodes: 35, v2: 96.2, real: 168.0, clean: 71.8, adjusted: 17.0, maintenance: 16.6, mixed: 16.7, cleaning: 13.1, maintLoad: 97.3 },
  { id: '2025-W42-7d', nodes: 33, v2: 106.7, real: 264.9, clean: 158.2, adjusted: 93.8, maintenance: 92.9, mixed: 87.9, cleaning: 19.1, maintLoad: 42.8 },
  { id: '2025-W43-7d', nodes: 26, v2: 72.9, real: 230.2, clean: 157.4, adjusted: 110.0, maintenance: 109.9, mixed: 112.8, cleaning: 13.1, maintLoad: 20.3 },
  { id: '2025-W44-7d', nodes: 22, v2: 36.7, real: 101.9, clean: 65.2, adjusted: 37.9, maintenance: 37.9, mixed: 31.7, cleaning: 11.5, maintLoad: 120.5 },
  { id: '2025-W45-7d', nodes: 31, v2: 80.4, real: 174.0, clean: 93.6, adjusted: 51.4, maintenance: 37.4, mixed: 45.8, cleaning: 6.1, maintLoad: 55.8 },
  { id: '2025-W46-7d', nodes: 38, v2: 81.4, real: 133.5, clean: 52.1, adjusted: 1.4, maintenance: -4.0, mixed: 0.5, cleaning: 8.6, maintLoad: 50.6 },
  { id: '2025-W47-7d', nodes: 32, v2: 75.4, real: 125.2, clean: 49.9, adjusted: 13.2, maintenance: 5.1, mixed: 17.8, cleaning: 5.3, maintLoad: 39.1 },
  { id: '2025-W48-7d', nodes: 32, v2: 78.5, real: 127.4, clean: 48.8, adjusted: 1.5, maintenance: 1.5, mixed: -2.0, cleaning: 14.8, maintLoad: 24.6 },
  { id: '2025-W49-7d', nodes: 29, v2: 80.4, real: 115.7, clean: 35.3, adjusted: 3.9, maintenance: 2.8, mixed: 2.4, cleaning: 19.4, maintLoad: 11.9 },
  { id: '2025-W50-7d', nodes: 19, v2: 57.8, real: 99.1, clean: 41.3, adjusted: 12.1, maintenance: 8.9, mixed: 7.1, cleaning: 8.4, maintLoad: 41.2 },
  { id: '2025-W51-7d', nodes: 35, v2: 69.0, real: 132.0, clean: 63.0, adjusted: 19.1, maintenance: 1.4, mixed: 16.5, cleaning: 12.1, maintLoad: 56.6 },
  { id: '2025-W52-7d', nodes: 15, v2: 27.3, real: 44.2, clean: 16.9, adjusted: 0.6, maintenance: 0.6, mixed: -0.6, cleaning: 0.5, maintLoad: 5.4 },
  { id: '2026-W01-7d', nodes: 8, v2: 14.8, real: 36.2, clean: 21.3, adjusted: 8.0, maintenance: -3.7, mixed: 5.7, cleaning: 13.4, maintLoad: 48.7 },
]

function isoWeekStart(year: number, week: number): Date {
  const jan4 = new Date(Date.UTC(year, 0, 4))
  const day = jan4.getUTCDay() || 7
  const monday = new Date(jan4)
  monday.setUTCDate(jan4.getUTCDate() - day + 1)
  const result = new Date(monday)
  result.setUTCDate(monday.getUTCDate() + (week - 1) * 7)
  return result
}

function fmtISO(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function datesForWindow(id: string): Pick<WeekImpact, 'week_start' | 'week_end'> {
  const match = id.match(/^(\d{4})-W(\d{2})/)
  if (!match) return { week_start: '', week_end: '' }

  const start = isoWeekStart(Number(match[1]), Number(match[2]))
  const end = new Date(start)
  end.setUTCDate(start.getUTCDate() + 6)
  return { week_start: fmtISO(start), week_end: fmtISO(end) }
}

const weeks: WeekImpact[] = ACTUAL_WEEK_REPLAY.map(week => ({
  week_id: week.id,
  ...datesForWindow(week.id),
  node_count: week.nodes,
  v2_makespan_h: week.v2,
  real_simulated_makespan_h: week.real,
  clean_saving_h: week.clean,
  adjusted_saving_h: week.adjusted,
  maintenance_adjusted_saving_h: week.maintenance,
  mixed_observed_saving_h: week.mixed,
  real_cleaning_h: week.cleaning,
  real_maintenance_rerun_h: week.maintLoad,
  has_production: week.nodes > 0,
}))

export const impactAtlas2025: ImpactAtlas = {
  year: 2025,
  source_dataset: 'services/optimizer/reports/optimizer_v2_makespan_comparison.csv',
  generated_at: '2026-05-24T09:25:16',
  weeks,
  windows_evaluated: 53,
  valid_solutions: 53,
  mean_v2_makespan_h: 85.03,
  mean_real_simulated_makespan_h: 158.54,
  clean_saving_h_per_week: 73.52,
  adjusted_saving_h_per_week: 23.15,
  adjusted_weeks_won: 49,
  maintenance_adjusted_saving_h_per_week: 14.15,
  maintenance_adjusted_weeks_won: 38,
  mixed_observed_saving_h_per_week: 18.35,
  mixed_observed_weeks_won: 43,
  mean_real_cleaning_h: 13.77,
  mean_real_maintenance_rerun_h: 50.29,
}
