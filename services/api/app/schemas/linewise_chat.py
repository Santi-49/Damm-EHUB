"""Pydantic schemas for the LineWise chat endpoint.

Mirrors apps/web/lib/types/chat.ts so the wire format matches what the
frontend already sends. Kept minimal on purpose — the LLM does the heavy
lifting; the API just shuttles messages.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ChatRole = Literal["user", "assistant", "system"]
ChatView = Literal["plan", "compare", "what-if", "insights"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str


class ChatScope(BaseModel):
    view: ChatView | None = None
    line_id: int | None = None
    slot_id: str | None = None
    transition_id: str | None = None
    sku_id: str | None = None
    dropped_sku_id: str | None = None


class ChatGrounding(BaseModel):
    """Optional view-data the frontend can send so the LLM can quote real
    numbers. Compare view sends S_real and S_opt context so the LLM can
    produce grounded reports from the two runs."""

    view: ChatView
    context: Any


class ChatRequest(BaseModel):
    solution_id: str
    scope: ChatScope = Field(default_factory=ChatScope)
    history: list[ChatMessage] = Field(default_factory=list)
    user_message: str
    grounding: ChatGrounding | None = None


class GroundingReference(BaseModel):
    kind: str
    ref_id: str


class ChatResponse(BaseModel):
    assistant_message: str
    referenced: list[GroundingReference] = Field(default_factory=list)
