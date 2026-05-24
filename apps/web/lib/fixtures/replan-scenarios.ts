import type { Sequence, SimulationReport } from '@/lib/types/linewise'
import { sequenceOpt, simulationOpt } from './index'

// ─── Shared L14 + L17 (unchanged in both scenarios) ────────────────────────
const l14Slots = sequenceOpt.slots.filter(s => s.line === 14)
const l17Slots = sequenceOpt.slots.filter(s => s.line === 17)

// ─── SCENARIO A: Urgent demand — +8 000 units FREQ-2/5-25 ──────────────────
// Only L19 can handle the 2/5 format. LineWise extends the FreqFresh blocks
// and trims RDSQ by 3.5 h (8 300 units shed, lowest margin on the line).
const seqReplanA: Sequence = {
  id:         'seq-replan-2026-w20-A',
  week_id:    '2026-W20',
  week_start: '2026-05-18T06:00:00',
  week_end:   '2026-05-24T22:00:00',
  source:     'replan',
  slots: [
    ...l14Slots,
    ...l17Slots,
    // L19 — first FREQ block extended (+5 000 units in same window)
    { id: 'l19r-A-s1', line: 19, start: '2026-05-18T06:00:00', end: '2026-05-18T07:00:00', kind: 'cleaning',   label: 'Line start cleaning' },
    { id: 'l19r-A-s2', line: 19, start: '2026-05-18T07:00:00', end: '2026-05-18T15:00:00', kind: 'production', sku: 'FREQ-2/5-25', label: 'FreqFresh 2/5 25cl', units: 27000, oee_expected: 0.78 },
    { id: 'l19r-A-s3', line: 19, start: '2026-05-18T15:00:00', end: '2026-05-18T17:30:00', kind: 'changeover', sku: 'FREQ-2/5-25', label: '→ Damm 1/3', changeover_h: 2.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change_2_5_to_1_3', impact_h: 1.8 }, { feature: 'brand_change', impact_h: 0.7 }] },
    { id: 'l19r-A-s4', line: 19, start: '2026-05-18T17:30:00', end: '2026-05-20T06:00:00', kind: 'production', sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 64000, oee_expected: 0.85 },
    { id: 'l19r-A-s5', line: 19, start: '2026-05-20T06:00:00', end: '2026-05-20T07:30:00', kind: 'changeover', sku: 'DAMM-1/3-33', label: '→ RedSq 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.2 }, { feature: 'format_same', impact_h: -0.1 }] },
    // RDSQ trimmed — ends 3.5 h earlier to free window for extra FREQ
    { id: 'l19r-A-s6', line: 19, start: '2026-05-20T07:30:00', end: '2026-05-21T18:30:00', kind: 'production', sku: 'RDSQ-1/3-33', label: 'RedSq 1/3 33cl (trimmed)', units: 46000, oee_expected: 0.82 },
    { id: 'l19r-A-s7', line: 19, start: '2026-05-21T18:30:00', end: '2026-05-22T02:30:00', kind: 'cleaning',   label: 'Night cleaning + format prep' },
    { id: 'l19r-A-s8', line: 19, start: '2026-05-22T02:30:00', end: '2026-05-22T05:00:00', kind: 'changeover', sku: 'RDSQ-1/3-33', label: '→ FreqFresh 2/5', changeover_h: 2.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change_1_3_to_2_5', impact_h: 1.9 }, { feature: 'brand_change', impact_h: 0.6 }] },
    // Second FREQ block — absorbs the extra 8 000 units of demand
    { id: 'l19r-A-s9', line: 19, start: '2026-05-22T05:00:00', end: '2026-05-23T22:00:00', kind: 'production', sku: 'FREQ-2/5-25', label: 'FreqFresh 2/5 25cl (extended)', units: 52000, oee_expected: 0.80 },
  ],
}

const simReplanA: SimulationReport = {
  sequence_id: 'seq-replan-2026-w20-A',
  oee_global:  0.817,
  h_changes:   17.0,
  h_productive: 289.5,
  coverage:    0.97,
  makespan_h:  136.0,
  oee_per_line: [
    { line: 14, oee: 0.831, h_productive: 98.0,  h_changeover: 7.5,  h_cleaning: 2.0, h_maintenance: 8.0, h_idle: 0.0, coverage: 1.0  },
    { line: 17, oee: 0.818, h_productive: 97.0,  h_changeover: 4.5,  h_cleaning: 2.0, h_maintenance: 0.0, h_idle: 0.0, coverage: 1.0  },
    { line: 19, oee: 0.802, h_productive: 94.5,  h_changeover: 5.0,  h_cleaning: 2.0, h_maintenance: 0.0, h_idle: 0.0, coverage: 0.91 },
  ],
  dropped_skus: [
    { sku: 'RDSQ-1/3-33', units_demanded: 54000, units_dropped: 8000, margin_lost: 1360,
      reason: 'RDSQ trimmed 3.5 h to free L19 capacity for urgent FREQ-2/5-25 demand' },
  ],
}

// ─── SCENARIO B: L14 breakdown — 8 h on Wed 20 May ─────────────────────────
// L14 goes dark 06:00–14:00. All subsequent L14 slots shift +8 h.
// ESTB-1/2 production is cut short; L19 absorbs a partial DAMM-1/2 run
// (both lines handle the 1/2 format). DAMM-1/2 units are partially dropped.
const seqReplanB: Sequence = {
  id:         'seq-replan-2026-w20-B',
  week_id:    '2026-W20',
  week_start: '2026-05-18T06:00:00',
  week_end:   '2026-05-24T22:00:00',
  source:     'replan',
  slots: [
    // L14 — breakdown inserted Wed 06:00-14:00; subsequent slots shift +8 h
    { id: 'l14r-B-s1',  line: 14, start: '2026-05-18T06:00:00', end: '2026-05-18T07:00:00', kind: 'cleaning',     label: 'Line start cleaning' },
    { id: 'l14r-B-s2',  line: 14, start: '2026-05-18T07:00:00', end: '2026-05-18T14:30:00', kind: 'production',   sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 28000, oee_expected: 0.82 },
    { id: 'l14r-B-s3',  line: 14, start: '2026-05-18T14:30:00', end: '2026-05-18T16:00:00', kind: 'changeover',   sku: 'DAMM-1/3-33', label: '→ EstB 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'format_same', impact_h: -0.2 }, { feature: 'day_monday', impact_h: 0.3 }] },
    { id: 'l14r-B-s4',  line: 14, start: '2026-05-18T16:00:00', end: '2026-05-19T06:00:00', kind: 'production',   sku: 'ESTB-1/3-33', label: 'EstB 1/3 33cl', units: 52000, oee_expected: 0.84 },
    { id: 'l14r-B-s5',  line: 14, start: '2026-05-19T06:00:00', end: '2026-05-19T07:30:00', kind: 'changeover',   sku: 'ESTB-1/3-33', label: '→ Voll 1/2', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change', impact_h: 1.1 }, { feature: 'brand_change', impact_h: 0.7 }, { feature: 'prev_oee_high', impact_h: -0.3 }] },
    { id: 'l14r-B-s6',  line: 14, start: '2026-05-19T07:30:00', end: '2026-05-20T06:00:00', kind: 'production',   sku: 'VOLL-1/2-50', label: 'Voll-Damm 1/2', units: 41000, oee_expected: 0.80 },
    // ⚠ BREAKDOWN — L14 offline Wed 06:00–14:00
    { id: 'l14r-B-inc', line: 14, start: '2026-05-20T06:00:00', end: '2026-05-20T14:00:00', kind: 'maintenance',  label: '⚠ Unplanned breakdown (8 h)' },
    // All subsequent L14 slots pushed +8 h
    { id: 'l14r-B-s7',  line: 14, start: '2026-05-20T14:00:00', end: '2026-05-20T15:00:00', kind: 'cleaning',     label: 'Mid-week clean' },
    { id: 'l14r-B-s8',  line: 14, start: '2026-05-20T15:00:00', end: '2026-05-20T16:30:00', kind: 'changeover',   sku: 'VOLL-1/2-50', label: '→ EstB 1/2', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 0.9 }, { feature: 'format_same', impact_h: -0.1 }] },
    // ESTB-1/2 block cut short — ends at Thu 22:00 instead of Fri 22:00
    { id: 'l14r-B-s9',  line: 14, start: '2026-05-20T16:30:00', end: '2026-05-21T22:00:00', kind: 'production',   sku: 'ESTB-1/2-50', label: 'EstB 1/2 50cl (short)', units: 31000, oee_expected: 0.85 },
    { id: 'l14r-B-s10', line: 14, start: '2026-05-21T22:00:00', end: '2026-05-22T06:00:00', kind: 'maintenance',  label: 'Planned maintenance' },
    { id: 'l14r-B-s11', line: 14, start: '2026-05-22T06:00:00', end: '2026-05-22T07:30:00', kind: 'changeover',   sku: 'ESTB-1/2-50', label: '→ Damm 1/2', changeover_h: 1.5, changeover_source: 'teorico',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.1 }, { feature: 'post_maintenance', impact_h: 0.4 }] },
    { id: 'l14r-B-s12', line: 14, start: '2026-05-22T07:30:00', end: '2026-05-23T22:00:00', kind: 'production',   sku: 'DAMM-1/2-50', label: 'Damm 1/2 50cl', units: 48000, oee_expected: 0.83 },

    // L17 — unchanged
    ...l17Slots,

    // L19 — absorbs a partial DAMM-1/2 run to compensate (L19 handles 1/2 format)
    { id: 'l19r-B-s1', line: 19, start: '2026-05-18T06:00:00', end: '2026-05-18T07:00:00', kind: 'cleaning',   label: 'Line start cleaning' },
    { id: 'l19r-B-s2', line: 19, start: '2026-05-18T07:00:00', end: '2026-05-18T15:00:00', kind: 'production', sku: 'FREQ-2/5-25', label: 'FreqFresh 2/5 25cl', units: 22000, oee_expected: 0.78 },
    { id: 'l19r-B-s3', line: 19, start: '2026-05-18T15:00:00', end: '2026-05-18T17:30:00', kind: 'changeover', sku: 'FREQ-2/5-25', label: '→ Damm 1/3', changeover_h: 2.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change_2_5_to_1_3', impact_h: 1.8 }, { feature: 'brand_change', impact_h: 0.7 }] },
    { id: 'l19r-B-s4', line: 19, start: '2026-05-18T17:30:00', end: '2026-05-20T06:00:00', kind: 'production', sku: 'DAMM-1/3-33', label: 'Damm 1/3 33cl', units: 64000, oee_expected: 0.85 },
    { id: 'l19r-B-s5', line: 19, start: '2026-05-20T06:00:00', end: '2026-05-20T07:30:00', kind: 'changeover', sku: 'DAMM-1/3-33', label: '→ RedSq 1/3', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'brand_change', impact_h: 1.2 }, { feature: 'format_same', impact_h: -0.1 }] },
    { id: 'l19r-B-s6', line: 19, start: '2026-05-20T07:30:00', end: '2026-05-21T22:00:00', kind: 'production', sku: 'RDSQ-1/3-33', label: 'RedSq 1/3 33cl', units: 54000, oee_expected: 0.82 },
    { id: 'l19r-B-s7', line: 19, start: '2026-05-21T22:00:00', end: '2026-05-22T06:00:00', kind: 'cleaning',   label: 'Night cleaning + format prep' },
    // Extra DAMM-1/2 run on L19 to absorb L14 overflow
    { id: 'l19r-B-s8', line: 19, start: '2026-05-22T06:00:00', end: '2026-05-22T07:30:00', kind: 'changeover', sku: 'RDSQ-1/3-33', label: '→ Damm 1/2 (L14 overflow)', changeover_h: 1.5, changeover_source: 'ml',
      changeover_drivers: [{ feature: 'format_change_1_3_to_1_2', impact_h: 1.1 }, { feature: 'brand_change', impact_h: 0.7 }, { feature: 'emergency_replan', impact_h: 0.3 }] },
    { id: 'l19r-B-s9', line: 19, start: '2026-05-22T07:30:00', end: '2026-05-23T22:00:00', kind: 'production', sku: 'DAMM-1/2-50', label: 'Damm 1/2 50cl (overflow from L14)', units: 20000, oee_expected: 0.80 },
  ],
}

const simReplanB: SimulationReport = {
  sequence_id: 'seq-replan-2026-w20-B',
  oee_global:  0.803,
  h_changes:   19.5,
  h_productive: 280.5,
  coverage:    0.94,
  makespan_h:  136.0,
  oee_per_line: [
    { line: 14, oee: 0.784, h_productive: 89.0,  h_changeover: 9.0,  h_cleaning: 2.0, h_maintenance: 16.0, h_idle: 0.0, coverage: 0.88 },
    { line: 17, oee: 0.818, h_productive: 97.0,  h_changeover: 4.5,  h_cleaning: 2.0, h_maintenance: 0.0,  h_idle: 0.0, coverage: 1.0  },
    { line: 19, oee: 0.807, h_productive: 94.5,  h_changeover: 6.0,  h_cleaning: 2.0, h_maintenance: 0.0,  h_idle: 0.0, coverage: 1.0  },
  ],
  dropped_skus: [
    { sku: 'ESTB-1/2-50', units_demanded: 56000, units_dropped: 25000, margin_lost: 6250,
      reason: 'L14 breakdown (8 h) compressed the ESTB-1/2 production window by 8 h' },
  ],
}

// ─── Public API ─────────────────────────────────────────────────────────────

export interface ReplanScenario {
  id:             string
  label:          string
  description:    string
  recommendation: {
    assignedLine?: 14 | 17 | 19
    headline:      string
    why:           string
    constraints:   string[]
  }
  sequence: Sequence
  report:   SimulationReport
  base:     SimulationReport
}

export const replanScenarios: ReplanScenario[] = [
  {
    id:          'urgent-demand',
    label:       'Urgent demand — +N units of selected SKU',
    description: 'Client orders 8 000 additional cans of FreqFresh 2/5. Where does LineWise fit them?',
    recommendation: {
      assignedLine: 19,
      headline:     'Assign extra FREQ-2/5-25 demand to L19',
      why:          'L19 is the only line in the plant that can handle the 2/5 (44 cl) format. L14 and L17 do not have the required filler head configuration.',
      constraints: [
        'L14 → 1/2 and 1/3 only (no 2/5 capability)',
        'L17 → 1/3 only (no 2/5 capability)',
        'L19 → 1/2, 1/3, 2/5 ✓ assigned',
      ],
    },
    sequence: seqReplanA,
    report:   simReplanA,
    base:     simulationOpt,
  },
  {
    id:          'l14-breakdown',
    label:       'Breakdown — Line X offline for Y hours',
    description: 'An unplanned mechanical failure takes L14 offline for 8 h on Wednesday morning.',
    recommendation: {
      assignedLine: 19,
      headline:     'Redistribute L14 overflow (1/2 format) to L19',
      why:          'L19 shares the 1/2 (50 cl) format capability with L14. L17 cannot handle 1/2 format and is ruled out. LineWise redirects the DAMM-1/2 overflow after FreqFresh finishes on L19.',
      constraints: [
        'L14 → offline until 14:00 Wed (8 h breakdown)',
        'L17 → 1/3 only (no 1/2 capability)',
        'L19 → 1/2 format ✓ absorbs overflow',
      ],
    },
    sequence: seqReplanB,
    report:   simReplanB,
    base:     simulationOpt,
  },
]
