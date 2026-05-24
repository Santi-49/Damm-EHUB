// Placeholder data for the sequence graph on the plan page.
// Models L17's SKU chain: nodes are SKU chunks, edges are changeover hours.
// `path: 'baseline'` = S_real (Blue Yonder / JDA order), `path: 'opt'` = LineWise.

export interface SeqGraphNode {
  id: string
  label: string
  /** SKU family — used for fill colour, matches gantt-chart family palette */
  family: 'DAMM' | 'ESTB' | 'DAURA' | 'LEMO' | 'FREQ' | 'RDSQ' | 'VOLL'
  /** Production volume in hectolitres — used to scale node size */
  volume_hl: number
  /** Manual layout — react-flow positions */
  x: number
  y: number
}

export interface SeqGraphEdge {
  id: string
  source: string
  target: string
  /** Changeover duration in hours */
  hours: number
  /** Which path this edge belongs to */
  path: 'baseline' | 'opt'
}

export const sequenceGraphLine17: { nodes: SeqGraphNode[]; edges: SeqGraphEdge[] } = {
  nodes: [
    { id: 'ED', label: 'Estrella 1/3', family: 'DAMM',  volume_hl: 480, x:  40, y: 200 },
    { id: 'XI', label: 'Xibeca 1/3',   family: 'DAURA', volume_hl: 420, x: 200, y:  60 },
    { id: 'FD', label: 'Free Damm',    family: 'FREQ',  volume_hl: 320, x: 380, y:  30 },
    { id: 'DL', label: 'Damm Lemon',   family: 'LEMO',  volume_hl: 380, x: 540, y:  90 },
    { id: 'KE', label: 'Keler 33CL',   family: 'RDSQ',  volume_hl: 260, x: 600, y: 240 },
    { id: 'TU', label: 'Turia 33CL',   family: 'VOLL',  volume_hl: 220, x: 380, y: 280 },
  ],
  edges: [
    // Baseline (S_real) order: ED → XI → FD → DL → TU → KE
    { id: 'b1', source: 'ED', target: 'XI', hours: 0.8, path: 'baseline' },
    { id: 'b2', source: 'XI', target: 'FD', hours: 2.1, path: 'baseline' },
    { id: 'b3', source: 'FD', target: 'DL', hours: 1.8, path: 'baseline' },
    { id: 'b4', source: 'DL', target: 'TU', hours: 0.9, path: 'baseline' },
    { id: 'b5', source: 'TU', target: 'KE', hours: 0.5, path: 'baseline' },
    // LineWise (S_opt) order: ED → XI → DL → FD → KE → TU
    { id: 'o1', source: 'ED', target: 'XI', hours: 0.8, path: 'opt' },
    { id: 'o2', source: 'XI', target: 'DL', hours: 0.3, path: 'opt' },
    { id: 'o3', source: 'DL', target: 'FD', hours: 0.4, path: 'opt' },
    { id: 'o4', source: 'FD', target: 'KE', hours: 0.5, path: 'opt' },
    { id: 'o5', source: 'KE', target: 'TU', hours: 0.5, path: 'opt' },
  ],
}
