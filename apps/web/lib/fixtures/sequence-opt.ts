import type { Sequence } from '@/lib/types/linewise'

// S_opt — LineWise optimised proposal for demo week 18-24 May 2026
export const sequenceOpt: Sequence = {
  id: 'seq-opt-2026-w20',
  week_id: '2026-W20',
  week_start: '2026-05-18T06:00:00',
  week_end:   '2026-05-24T22:00:00',
  source: 'opt',
  slots: [
    // ─── LINE 14 ──────────────────────────────────────────────────────────────
    // L14 handles 1/2 and 1/3 formats
    { id: 'l14-s1',  line: 14, start: '2026-05-18T06:00:00', end: '2026-05-18T07:00:00', kind: 'cleaning',    label: 'Line start cleaning' },
    { id: 'l14-s2',  line: 14, start: '2026-05-18T07:00:00', end: '2026-05-18T14:30:00', kind: 'production',  sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 28000, oee_expected: 0.82 },
    { id: 'l14-s3',  line: 14, start: '2026-05-18T14:30:00', end: '2026-05-18T16:00:00', kind: 'changeover',  sku: 'DAMM-1/3-33', label: '→ EstB 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'format_same', impact_h: -0.2 }, { feature: 'day_monday', impact_h: 0.3 }] },
    { id: 'l14-s4',  line: 14, start: '2026-05-18T16:00:00', end: '2026-05-19T06:00:00', kind: 'production',  sku: 'ESTB-1/3-33', label: 'EstB 1/3 33cl', units: 52000, oee_expected: 0.84 },
    { id: 'l14-s5',  line: 14, start: '2026-05-19T06:00:00', end: '2026-05-19T07:30:00', kind: 'changeover',  sku: 'ESTB-1/3-33', label: '→ Voll 1/2', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change', impact_h: 1.1 }, { feature: 'brand_change', impact_h: 0.7 }, { feature: 'prev_oee_high', impact_h: -0.3 }] },
    { id: 'l14-s6',  line: 14, start: '2026-05-19T07:30:00', end: '2026-05-20T06:00:00', kind: 'production',  sku: 'VOLL-1/2-50', label: 'Voll-Damm 1/2', units: 41000, oee_expected: 0.80 },
    { id: 'l14-s7',  line: 14, start: '2026-05-20T06:00:00', end: '2026-05-20T07:00:00', kind: 'cleaning',    label: 'Mid-week clean' },
    { id: 'l14-s8',  line: 14, start: '2026-05-20T07:00:00', end: '2026-05-20T08:30:00', kind: 'changeover',  sku: 'VOLL-1/2-50', label: '→ EstB 1/2', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'format_same', impact_h: -0.1 }] },
    { id: 'l14-s9',  line: 14, start: '2026-05-20T08:30:00', end: '2026-05-21T22:00:00', kind: 'production',  sku: 'ESTB-1/2-50', label: 'EstB 1/2 50cl', units: 56000, oee_expected: 0.85 },
    { id: 'l14-s10', line: 14, start: '2026-05-21T22:00:00', end: '2026-05-22T06:00:00', kind: 'maintenance', label: 'Planned maintenance' },
    { id: 'l14-s11', line: 14, start: '2026-05-22T06:00:00', end: '2026-05-22T07:30:00', kind: 'changeover',  sku: 'ESTB-1/2-50', label: '→ Damm 1/2', changeover_h: 1.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.1 }, { feature: 'post_maintenance', impact_h: 0.4 }] },
    { id: 'l14-s12', line: 14, start: '2026-05-22T07:30:00', end: '2026-05-23T22:00:00', kind: 'production',  sku: 'DAMM-1/2-50', label: 'Damm 1/2 50cl', units: 48000, oee_expected: 0.83 },

    // ─── LINE 17 ──────────────────────────────────────────────────────────────
    // L17 handles 1/3 only
    { id: 'l17-s1',  line: 17, start: '2026-05-18T06:00:00', end: '2026-05-18T07:00:00', kind: 'cleaning',    label: 'Line start cleaning' },
    { id: 'l17-s2',  line: 17, start: '2026-05-18T07:00:00', end: '2026-05-19T14:00:00', kind: 'production',  sku: 'ESTB-1/3-33', label: 'EstB 1/3 33cl', units: 62000, oee_expected: 0.86 },
    { id: 'l17-s3',  line: 17, start: '2026-05-19T14:00:00', end: '2026-05-19T15:00:00', kind: 'changeover',  sku: 'ESTB-1/3-33', label: '→ Daura 1/3', changeover_h: 1.0, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.8 }, { feature: 'format_same', impact_h: -0.1 }, { feature: 'line_17_efficiency', impact_h: 0.3 }] },
    { id: 'l17-s4',  line: 17, start: '2026-05-19T15:00:00', end: '2026-05-20T22:00:00', kind: 'production',  sku: 'DAURA-1/3-33', label: 'Daura 1/3 33cl', units: 44000, oee_expected: 0.81 },
    { id: 'l17-s5',  line: 17, start: '2026-05-20T22:00:00', end: '2026-05-21T06:00:00', kind: 'cleaning',    label: 'Night cleaning' },
    { id: 'l17-s6',  line: 17, start: '2026-05-21T06:00:00', end: '2026-05-21T07:30:00', kind: 'changeover',  sku: 'DAURA-1/3-33', label: '→ Lemon 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.0 }, { feature: 'allergen_clean', impact_h: 0.5 }] },
    { id: 'l17-s7',  line: 17, start: '2026-05-21T07:30:00', end: '2026-05-22T20:00:00', kind: 'production',  sku: 'LEMO-1/3-33', label: 'Lemon 1/3 33cl', units: 38000, oee_expected: 0.79 },
    { id: 'l17-s8',  line: 17, start: '2026-05-22T20:00:00', end: '2026-05-22T21:30:00', kind: 'changeover',  sku: 'LEMO-1/3-33', label: '→ Damm 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'format_same', impact_h: -0.2 }] },
    { id: 'l17-s9',  line: 17, start: '2026-05-22T21:30:00', end: '2026-05-23T22:00:00', kind: 'production',  sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 32000, oee_expected: 0.83 },

    // ─── LINE 19 ──────────────────────────────────────────────────────────────
    // L19 handles 1/2, 1/3 and 2/5 formats
    { id: 'l19-s1',  line: 19, start: '2026-05-18T06:00:00', end: '2026-05-18T07:00:00', kind: 'cleaning',    label: 'Line start cleaning' },
    { id: 'l19-s2',  line: 19, start: '2026-05-18T07:00:00', end: '2026-05-18T15:00:00', kind: 'production',  sku: 'FREQ-2/5-25', label: 'FreqFresh 2/5 25cl', units: 22000, oee_expected: 0.78 },
    { id: 'l19-s3',  line: 19, start: '2026-05-18T15:00:00', end: '2026-05-18T17:30:00', kind: 'changeover',  sku: 'FREQ-2/5-25', label: '→ Damm 1/3', changeover_h: 2.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change_2_5_to_1_3', impact_h: 1.8 }, { feature: 'brand_change', impact_h: 0.7 }] },
    { id: 'l19-s4',  line: 19, start: '2026-05-18T17:30:00', end: '2026-05-20T06:00:00', kind: 'production',  sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 64000, oee_expected: 0.85 },
    { id: 'l19-s5',  line: 19, start: '2026-05-20T06:00:00', end: '2026-05-20T07:30:00', kind: 'changeover',  sku: 'DAMM-1/3-33', label: '→ RedSq 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.2 }, { feature: 'format_same', impact_h: -0.1 }] },
    { id: 'l19-s6',  line: 19, start: '2026-05-20T07:30:00', end: '2026-05-21T22:00:00', kind: 'production',  sku: 'RDSQ-1/3-33', label: 'RedSq 1/3 33cl', units: 54000, oee_expected: 0.82 },
    { id: 'l19-s7',  line: 19, start: '2026-05-21T22:00:00', end: '2026-05-22T06:00:00', kind: 'cleaning',    label: 'Night cleaning + format prep' },
    { id: 'l19-s8',  line: 19, start: '2026-05-22T06:00:00', end: '2026-05-22T08:30:00', kind: 'changeover',  sku: 'RDSQ-1/3-33', label: '→ FreqFresh 2/5', changeover_h: 2.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change_1_3_to_2_5', impact_h: 1.9 }, { feature: 'brand_change', impact_h: 0.6 }] },
    { id: 'l19-s9',  line: 19, start: '2026-05-22T08:30:00', end: '2026-05-23T22:00:00', kind: 'production',  sku: 'FREQ-2/5-25', label: 'FreqFresh 2/5 25cl', units: 44000, oee_expected: 0.80 },
  ],
}
