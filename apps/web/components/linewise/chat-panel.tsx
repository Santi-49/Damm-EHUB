'use client'

// LineWise chat panel.
//
// Behaviour:
//   1. Renders any `seedMessages` as the opening turns (the "intro" the LLM
//      would generate from the ExplanationPack once the backend is wired up).
//   2. On send, POSTs a ChatRequest to /api/v1/linewise/chat. If the backend
//      is unavailable, the API client falls back to a scope-aware canned reply.
//   3. Tracks a loading state ("typing" dots) while the request is in flight.
//
// The component does NOT manage cross-page conversation persistence — each
// page mounts its own panel with its own seeds.

import { useEffect, useRef, useState } from 'react'
import { RotateCcw, Send, Sparkles } from 'lucide-react'
import type {
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ChatScope,
} from '@/lib/types/chat'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { sendChatMessage, type DataSource } from '@/lib/linewise-api'
import { useChatHistory } from '@/lib/hooks/use-chat-history'

interface ChatPanelProps {
  solutionId: string
  scope: ChatScope
  seedMessages: ChatMessage[]
  title?: string
  subtitle?: string
  placeholder?: string
}

export function ChatPanel({
  solutionId,
  scope,
  seedMessages,
  title = 'LineWise assistant',
  subtitle = 'Grounded on the optimiser explanation pack',
  placeholder = 'Ask why a SKU went to this line, what drove a changeover, what changed vs last week…',
}: ChatPanelProps) {
  // Conversation lives in localStorage, keyed per-view, so users can refresh
  // or navigate away and pick up where they left off. The seed messages are
  // the initial state — once any real turn happens, that's what's persisted.
  const historyKey = `linewise_chat_${scope.view ?? 'default'}`
  const { messages, setMessages, clear } = useChatHistory(historyKey, seedMessages)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [lastSource, setLastSource] = useState<DataSource | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, pending])

  async function handleSend() {
    const text = input.trim()
    if (!text || pending) return

    const userMessage: ChatMessage = { role: 'user', content: text }
    const history = messages
    setMessages([...messages, userMessage])
    setInput('')
    setPending(true)

    const req: ChatRequest = {
      solution_id: solutionId,
      scope,
      history,
      user_message: text,
    }

    const response = await sendChatMessage(req)
    const data: ChatResponse = response.data

    setPending(false)
    setLastSource(response.source)
    setMessages(curr => [...curr, { role: 'assistant', content: data.assistant_message }])
  }

  const scopeChips: string[] = [
    scope.view && `view: ${scope.view}`,
    scope.line_id != null && `L${scope.line_id}`,
    scope.transition_id && `transition: ${scope.transition_id}`,
    scope.slot_id && `slot: ${scope.slot_id}`,
    scope.sku_id && `sku: ${scope.sku_id}`,
    scope.dropped_sku_id && `dropped: ${scope.dropped_sku_id}`,
  ].filter(Boolean) as string[]

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              {title}
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            {scopeChips.length > 0 && (
              <div className="flex flex-wrap gap-1 justify-end max-w-[60%]">
                {lastSource && (
                  <Badge variant={lastSource === 'backend' ? 'default' : 'outline'} className="text-[10px]">
                    {lastSource === 'backend' ? 'Backend' : 'Mock'}
                  </Badge>
                )}
                {scopeChips.map(chip => (
                  <Badge key={chip} variant="secondary" className="text-[10px] font-mono">
                    {chip}
                  </Badge>
                ))}
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={clear}
              disabled={pending || messages.length <= seedMessages.length}
              className="h-7 px-2 text-xs text-muted-foreground"
              aria-label="Clear conversation"
              title="Clear conversation"
            >
              <RotateCcw className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div
          ref={scrollRef}
          className="h-[280px] overflow-y-auto px-4 py-3 space-y-3 bg-muted/10"
        >
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={[
                  'max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed',
                  m.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-card border',
                ].join(' ')}
              >
                {m.content}
              </div>
            </div>
          ))}
          {pending && (
            <div className="flex justify-start">
              <div className="rounded-lg px-3 py-2 text-sm bg-card border text-muted-foreground">
                <TypingDots />
              </div>
            </div>
          )}
        </div>
        <div className="border-t bg-background p-3 flex items-end gap-2">
          <Textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={placeholder}
            className="min-h-[40px] max-h-[120px] resize-none"
            disabled={pending}
          />
          <Button
            onClick={handleSend}
            disabled={pending || !input.trim()}
            size="icon"
            className="shrink-0"
            aria-label="Send"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1 items-center">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-pulse" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-pulse [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-pulse [animation-delay:300ms]" />
    </span>
  )
}
