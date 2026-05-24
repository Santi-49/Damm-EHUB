"""LineWise chat endpoint — LangChain + Anthropic Claude.

Flow per turn:
  1. Frontend POSTs a ChatRequest (history + scope + user_message).
  2. We turn that into LangChain messages, prepend a system prompt with the
     LineWise domain primer, and call ChatAnthropic.ainvoke.
  3. Return the assistant text in ChatResponse.

The frontend holds the conversation history in localStorage, so this endpoint
is stateless — every call is the full conversation. Once we ground on the
real ExplanationPack we'll add the grounding payload to the system prompt
(see ChatRequest.grounding, optional).

If ``ANTHROPIC_API_KEY`` is empty we fall back to a canned reply so the demo
still works without a key.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import settings
from app.schemas.linewise_chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linewise", tags=["linewise"])


SYSTEM_PROMPT = """You are LineWise, an AI assistant embedded in a production planning tool for Damm's beer canning plant at El Prat.

Your job: help operators and planners understand why the optimiser produced a particular plan, why a transition was expensive, what a what-if scenario would do, or why an SKU was dropped. Always ground in the data shown in the conversation — never invent numbers.

Style:
- Concise. 2–4 sentences typical, unless the user asks for detail.
- Plain language. Operators read this, not data scientists.
- Quote specific numbers when you have them (e.g. "DAMM-1/3 dropped 4000 units, costing €720").
- If asked about something not in the context, say so honestly.

Domain primer:
- 3 canning lines: L14 (1/2 + 1/3 formats), L17 (1/3 only), L19 (1/2 + 1/3 + 2/5).
- Format codes: 1/2 = 50 cl, 1/3 = 33 cl, 2/5 = 44 cl.
- OEE = Availability × Performance × Quality. Quality ≡ 1 in this dataset.
- A "changeover" is the setup time between two consecutive SKUs on the same line.
- "S_real" = what actually ran. "S_opt" = the LineWise proposal.
- Demand is bucketed by week. The optimiser is m-TSP with a makespan objective and margin-aware disjunctions (it can drop low-margin SKUs when capacity is short)."""


def _to_lc_messages(req: ChatRequest) -> list[SystemMessage | HumanMessage | AIMessage]:
    """Convert a ChatRequest into a LangChain message list."""
    messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=SYSTEM_PROMPT)
    ]

    # Optional grounding — once the frontend starts populating it.
    if req.grounding is not None:
        messages.append(
            SystemMessage(
                content=(
                    f"Current view: {req.grounding.view}.\n"
                    f"Scope: {req.scope.model_dump(exclude_none=True)}\n\n"
                    f"View data (use this to quote numbers):\n{req.grounding.context}"
                )
            )
        )
    elif req.scope and req.scope.view:
        messages.append(SystemMessage(content=f"User is currently on the '{req.scope.view}' view."))

    for msg in req.history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
        # System messages from history are intentionally dropped — we own the system prompt.

    messages.append(HumanMessage(content=req.user_message))
    return messages


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # No key? Return a clear placeholder so the frontend's "Backend" badge
    # still lights up but the user knows wiring is incomplete.
    if not settings.anthropic_api_key:
        return ChatResponse(
            assistant_message=(
                "Chat backend is reachable but no ANTHROPIC_API_KEY is configured. "
                "Set it in services/api/.env and restart the API to start getting real answers."
            ),
            referenced=[],
        )

    llm = ChatAnthropic(
        model_name=settings.chat_model,
        max_tokens_to_sample=settings.chat_max_tokens,
        api_key=settings.anthropic_api_key,
        timeout=30,
        stop=None,
    )

    messages = _to_lc_messages(req)

    try:
        result = await llm.ainvoke(messages)
    except Exception as exc:  # noqa: BLE001 — surface any provider error verbatim
        logger.exception("LineWise chat: LLM call failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {exc}",
        ) from exc

    # LangChain returns the assistant content as str | list[ContentBlock].
    if isinstance(result.content, str):
        text = result.content
    else:
        text = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in result.content
        )

    return ChatResponse(assistant_message=text.strip(), referenced=[])
