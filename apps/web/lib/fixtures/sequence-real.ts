import type { Sequence } from '@/lib/types/linewise'

// S_real — what actually happened on the demo week 18-24 May 2026
// Key differences vs S_opt that tell the demo story:
//  L14: format change EstB-1/3 → Voll-1/2 took 3.5h instead of 1.5h
//  L17: Daura → Lemon did allergen clean but took 3.0h instead of 1.5h
//  L19: RedSq → FreqFresh forced a detour through L14 due to an unexpected incident on L19
export const sequenceReal: Sequence = {
  id: 'seq-real-2026-w20',
  week_id: '2026-W20',
  week_start: '2026-05-18T06:00:00',
  week_end:   '2026-05-24T22:00:00',
  source: 'real',
  slots: [
    // ─── LINE 14 ──────────────────────────────────────────────────────────────
    { id: 'l14r-s1',  line: 14, start: '2026-05-18T06:00:00', end: '2026-05-18T07:30:00', kind: 'cleaning',    label: 'Line start cleaning (overrun)' },
    { id: 'l14r-s2',  line: 14, start: '2026-05-18T07:30:00', end: '2026-05-18T15:00:00', kind: 'production',  sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 25000, oee_expected: 0.82, oee_actual: 0.74 },
    // Slow changeover — took 3.5h vs 1.5h expected (brand + format change penalty)
    { id: 'l14r-s3',  line: 14, start: '2026-05-18T15:00:00', end: '2026-05-18T18:30:00', kind: 'changeover',  sku: 'DAMM-1/3-33', label: '→ EstB 1/3 (overrun)', changeover_h: 3.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'cleaning_issue', impact_h: 1.2 }, { feature: 'monday_staffing', impact_h: 0.9 }] },
    { id: 'l14r-s4',  line: 14, start: '2026-05-18T18:30:00', end: '2026-05-19T06:00:00', kind: 'production',  sku: 'ESTB-1/3-33', label: 'EstB 1/3 33cl', units: 39000, oee_expected: 0.84, oee_actual: 0.80 },
    // Format change 1/3 → 1/2 also ran long
    { id: 'l14r-s5',  line: 14, start: '2026-05-19T06:00:00', end: '2026-05-19T09:30:00', kind: 'changeover',  sku: 'ESTB-1/3-33', label: '→ Voll 1/2 (overrun)', changeover_h: 3.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'format_change', impact_h: 1.1 }, { feature: 'brand_change', impact_h: 0.7 }, { feature: 'seal_adjustment', impact_h: 1.2 }] },
    { id: 'l14r-s6',  line: 14, start: '2026-05-19T09:30:00', end: '2026-05-20T06:00:00', kind: 'production',  sku: 'VOLL-1/2-50', label: 'Voll-Damm 1/2', units: 34000, oee_expected: 0.80, oee_actual: 0.76 },
    { id: 'l14r-s7',  line: 14, start: '2026-05-20T06:00:00', end: '2026-05-20T07:30:00', kind: 'cleaning',    label: 'Mid-week clean' },
    { id: 'l14r-s8',  line: 14, start: '2026-05-20T07:30:00', end: '2026-05-20T10:00:00', kind: 'changeover',  sku: 'VOLL-1/2-50', label: '→ EstB 1/2 (slow)', changeover_h: 2.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'post_night', impact_h: 0.8 }, { feature: 'format_same', impact_h: -0.1 }] },
    { id: 'l14r-s9',  line: 14, start: '2026-05-20T10:00:00', end: '2026-05-21T22:00:00', kind: 'production',  sku: 'ESTB-1/2-50', label: 'EstB 1/2 50cl', units: 48000, oee_expected: 0.85, oee_actual: 0.82 },
    { id: 'l14r-s10', line: 14, start: '2026-05-21T22:00:00', end: '2026-05-22T06:00:00', kind: 'maintenance', label: 'Planned maintenance' },
    { id: 'l14r-s11', line: 14, start: '2026-05-22T06:00:00', end: '2026-05-22T08:30:00', kind: 'changeover',  sku: 'ESTB-1/2-50', label: '→ Damm 1/2', changeover_h: 2.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.1 }, { feature: 'post_maintenance', impact_h: 0.4 }, { feature: 'morning_ramp', impact_h: 0.7 }] },
    { id: 'l14r-s12', line: 14, start: '2026-05-22T08:30:00', end: '2026-05-23T22:00:00', kind: 'production',  sku: 'DAMM-1/2-50', label: 'Damm 1/2 50cl', units: 43000, oee_expected: 0.83, oee_actual: 0.79 },

    // ─── LINE 17 ──────────────────────────────────────────────────────────────
    { id: 'l17r-s1',  line: 17, start: '2026-05-18T06:00:00', end: '2026-05-18T07:30:00', kind: 'cleaning',    label: 'Line start cleaning' },
    { id: 'l17r-s2',  line: 17, start: '2026-05-18T07:30:00', end: '2026-05-19T14:00:00', kind: 'production',  sku: 'ESTB-1/3-33', label: 'EstB 1/3 33cl', units: 59000, oee_expected: 0.86, oee_actual: 0.84 },
    { id: 'l17r-s3',  line: 17, start: '2026-05-19T14:00:00', end: '2026-05-19T15:30:00', kind: 'changeover',  sku: 'ESTB-1/3-33', label: '→ Daura 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.8 }, { feature: 'format_same', impact_h: -0.1 }, { feature: 'afternoon_crew', impact_h: 0.8 }] },
    { id: 'l17r-s4',  line: 17, start: '2026-05-19T15:30:00', end: '2026-05-20T22:00:00', kind: 'production',  sku: 'DAURA-1/3-33', label: 'Daura 1/3 33cl', units: 43000, oee_expected: 0.81, oee_actual: 0.79 },
    { id: 'l17r-s5',  line: 17, start: '2026-05-20T22:00:00', end: '2026-05-21T06:00:00', kind: 'cleaning',    label: 'Night cleaning' },
    // Allergen clean for Lemon took 3h instead of 1.5h — worst transition of the week
    { id: 'l17r-s6',  line: 17, start: '2026-05-21T06:00:00', end: '2026-05-21T09:00:00', kind: 'changeover',  sku: 'DAURA-1/3-33', label: '→ Lemon 1/3 (allergen overrun)', changeover_h: 3.0, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.0 }, { feature: 'allergen_clean', impact_h: 0.5 }, { feature: 'clean_protocol_deviation', impact_h: 1.2 }, { feature: 'inspector_wait', impact_h: 0.3 }] },
    { id: 'l17r-s7',  line: 17, start: '2026-05-21T09:00:00', end: '2026-05-22T20:00:00', kind: 'production',  sku: 'LEMO-1/3-33', label: 'Lemon 1/3 33cl', units: 34000, oee_expected: 0.79, oee_actual: 0.75 },
    { id: 'l17r-s8',  line: 17, start: '2026-05-22T20:00:00', end: '2026-05-22T21:30:00', kind: 'changeover',  sku: 'LEMO-1/3-33', label: '→ Damm 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'format_same', impact_h: -0.2 }] },
    { id: 'l17r-s9',  line: 17, start: '2026-05-22T21:30:00', end: '2026-05-23T22:00:00', kind: 'production',  sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 29000, oee_expected: 0.83, oee_actual: 0.81 },

    // ─── LINE 19 ──────────────────────────────────────────────────────────────
    { id: 'l19r-s1',  line: 19, start: '2026-05-18T06:00:00', end: '2026-05-18T07:00:00', kind: 'cleaning',    label: 'Line start cleaning' },
    { id: 'l19r-s2',  line: 19, start: '2026-05-18T07:00:00', end: '2026-05-18T15:00:00', kind: 'production',  sku: 'FREQ-2/5-25', label: 'FreqFresh 2/5 25cl', units: 19000, oee_expected: 0.78, oee_actual: 0.71 },
    // Long format changeover 2/5 → 1/3 (real was 3.5h vs opt 2.5h)
    { id: 'l19r-s3',  line: 19, start: '2026-05-18T15:00:00', end: '2026-05-18T18:30:00', kind: 'changeover',  sku: 'FREQ-2/5-25', label: '→ Damm 1/3 (format overrun)', changeover_h: 3.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'format_change_2_5_to_1_3', impact_h: 1.8 }, { feature: 'brand_change', impact_h: 0.7 }, { feature: 'filler_adjustment', impact_h: 1.0 }] },
    { id: 'l19r-s4',  line: 19, start: '2026-05-18T18:30:00', end: '2026-05-20T06:00:00', kind: 'production',  sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 60000, oee_expected: 0.85, oee_actual: 0.82 },
    { id: 'l19r-s5',  line: 19, start: '2026-05-20T06:00:00', end: '2026-05-20T07:30:00', kind: 'changeover',  sku: 'DAMM-1/3-33', label: '→ RedSq 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.2 }, { feature: 'format_same', impact_h: -0.1 }] },
    { id: 'l19r-s6',  line: 19, start: '2026-05-20T07:30:00', end: '2026-05-21T22:00:00', kind: 'production',  sku: 'RDSQ-1/3-33', label: 'RedSq 1/3 33cl', units: 50000, oee_expected: 0.82, oee_actual: 0.79 },
    { id: 'l19r-s7',  line: 19, start: '2026-05-21T22:00:00', end: '2026-05-22T06:00:00', kind: 'cleaning',    label: 'Night cleaning + format prep' },
    // Format 1/3 → 2/5 ran extremely long (3.5h vs 2.5h expected)
    { id: 'l19r-s8',  line: 19, start: '2026-05-22T06:00:00', end: '2026-05-22T09:30:00', kind: 'changeover',  sku: 'RDSQ-1/3-33', label: '→ FreqFresh 2/5 (overrun)', changeover_h: 3.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'format_change_1_3_to_2_5', impact_h: 1.9 }, { feature: 'brand_change', impact_h: 0.6 }, { feature: 'filler_recalibration', impact_h: 1.0 }] },
    { id: 'l19r-s9',  line: 19, start: '2026-05-22T09:30:00', end: '2026-05-23T22:00:00', kind: 'production',  sku: 'FREQ-2/5-25', label: 'FreqFresh 2/5 25cl', units: 41000, oee_expected: 0.80, oee_actual: 0.77 },
  ],
}
