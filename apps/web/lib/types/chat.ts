// Chat domain types — mirrors packages/contracts/module/chat.py
//
// The chat is fully LLM-powered and lives on the backend. Per-turn flow:
//   1. Frontend POSTs a ChatRequest (history + current view scope + new user message).
//   2. Backend loads the ExplanationPack for solution_id, slices it by scope,
//      prompts an LLM with the slice + history, and returns ChatResponse.
//   3. Frontend renders the assistant_message and (optionally) uses
//      `referenced` to highlight slots/transitions in the Gantt.
//
// The frontend owns suggested-question UX; the backend does not generate suggestions.

import type { GroundingKind } from './explainability'
import type { Line } from './linewise'

export type ChatRole = 'user' | 'assistant' | 'system'

export type ChatView = 'plan' | 'compare' | 'what-if' | 'insights'

export interface ChatMessage {
  role: ChatRole
  content: string
}

/**
 * What the user is currently looking at in the UI. All fields optional — set
 * only the ones that apply. The backend uses these to focus the LLM's
 * grounding on the relevant slice of the ExplanationPack.
 *
 * Example — planner clicked a Wednesday changeover on L14:
 *   { view: 'plan', line_id: 14, transition_id: '14:slot_023->slot_024' }
 */
export interface ChatScope {
  view?: ChatView
  line_id?: Line
  slot_id?: string
  transition_id?: string
  sku_id?: string
  dropped_sku_id?: string
}

/**
 * One turn from the frontend. For the very first turn (welcome / solution
 * narration), send an empty `history` and a seed `user_message` agreed with
 * the backend, e.g. "<<intro>>".
 */
export interface ChatRequest {
  /** Which ExplanationPack the backend should ground on. */
  solution_id: string
  scope: ChatScope
  /** Prior turns, oldest first. Excludes the just-typed user_message. */
  history: ChatMessage[]
  user_message: string
}

/**
 * A pointer to a fact in the ExplanationPack the assistant used. The UI can
 * use these to highlight the slot / transition / theme the answer is about —
 * e.g. flash the Gantt edge that backs a sentence.
 */
export interface GroundingReference {
  kind: GroundingKind
  /** e.g. slot_id, transition_id, theme_id, counterfactual_id */
  ref_id: string
}

export interface ChatResponse {
  assistant_message: string
  /** Best-effort. May be empty if the implementation doesn't extract groundings. */
  referenced?: GroundingReference[]
}
