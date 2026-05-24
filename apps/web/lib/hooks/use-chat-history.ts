'use client'

// Persist a per-view chat conversation in localStorage.
//
// Two-phase init avoids a Next.js hydration mismatch: the first render uses
// the seed (matches the server render), then a post-mount effect loads any
// saved transcript and replaces the messages. Subsequent state changes are
// flushed back to localStorage.

import { useEffect, useState } from 'react'
import type { ChatMessage } from '@/lib/types/chat'

interface UseChatHistoryReturn {
  messages: ChatMessage[]
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  clear: () => void
  hydrated: boolean
}

export function useChatHistory(storageKey: string, seed: ChatMessage[]): UseChatHistoryReturn {
  const [messages, setMessages] = useState<ChatMessage[]>(seed)
  const [hydrated, setHydrated] = useState(false)

  // Load saved transcript after mount — server render still shows the seed.
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(storageKey)
      if (raw) {
        const parsed = JSON.parse(raw) as ChatMessage[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed)
        }
      }
    } catch {
      // Corrupt JSON — ignore and keep the seed.
    }
    setHydrated(true)
    // Intentionally only run on key change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey])

  // Persist after we've hydrated, so the seed doesn't overwrite a real transcript.
  useEffect(() => {
    if (!hydrated || typeof window === 'undefined') return
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(messages))
    } catch {
      // Quota exceeded / private mode — ignore.
    }
  }, [storageKey, messages, hydrated])

  const clear = () => {
    setMessages(seed)
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(storageKey)
      } catch {}
    }
  }

  return { messages, setMessages, clear, hydrated }
}
