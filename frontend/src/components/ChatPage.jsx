import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Star, RefreshCw, ChevronDown, AlertCircle } from 'lucide-react'
import { v4 as uuid } from 'crypto'
import useStore from '../lib/store'
import { streamChat } from '../lib/api'
import ChatMessage from './ChatMessage'
import BirthForm from './BirthForm'
import StarField from './StarField'
import styles from './ChatPage.module.css'

const SUGGESTIONS = [
  "What does my birth chart say about my personality?",
  "What are today's planetary transits for me?",
  "Tell me about my career path based on my chart.",
  "What does Venus in my chart say about love?",
]

function genId() {
  return Math.random().toString(36).slice(2)
}

export default function ChatPage() {
  const messages = useStore((s) => s.messages)
  const addMessage = useStore((s) => s.addMessage)
  const updateLastAssistant = useStore((s) => s.updateLastAssistant)
  const isStreaming = useStore((s) => s.isStreaming)
  const setIsStreaming = useStore((s) => s.setIsStreaming)
  const sessionId = useStore((s) => s.sessionId)
  const setSessionId = useStore((s) => s.setSessionId)
  const birthDetails = useStore((s) => s.birthDetails)
  const showBirthForm = useStore((s) => s.showBirthForm)
  const setShowBirthForm = useStore((s) => s.setShowBirthForm)
  const clearMessages = useStore((s) => s.clearMessages)

  const [input, setInput] = useState('')
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  // Init session ID
  useEffect(() => {
    if (!sessionId) setSessionId(genId())
  }, [])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || isStreaming) return

    setInput('')
    setError(null)
    setIsStreaming(true)

    // Add user message
    addMessage({ id: genId(), role: 'user', content: text })

    // Add placeholder assistant message
    const assistantId = genId()
    addMessage({ id: assistantId, role: 'assistant', content: '', toolEvents: [], isStreaming: true })

    try {
      await streamChat({
        message: text,
        sessionId,
        birthDetails,
        onToken: (token) => {
          updateLastAssistant((prev) => ({ content: (prev.content || '') + token }))
        },
        onToolCall: (evt) => {
          updateLastAssistant((prev) => ({
            toolEvents: [...(prev.toolEvents || []), evt],
          }))
        },
        onDone: () => {
          updateLastAssistant({ isStreaming: false })
        },
        onError: (msg) => {
          setError(msg)
          updateLastAssistant({ content: 'I encountered an issue. Please try again.', isStreaming: false })
        },
      })
    } catch (err) {
      setError(err.message)
      updateLastAssistant({ content: 'Connection error. Is the backend running?', isStreaming: false })
    } finally {
      setIsStreaming(false)
    }
  }, [input, isStreaming, sessionId, birthDetails])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const isEmpty = messages.length === 0

  return (
    <div className={styles.page}>
      <StarField />

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.logo}>
          <span className={styles.logoStar}>✦</span>
          <span className={styles.logoText}>Aradhana</span>
        </div>

        <div className={styles.headerActions}>
          {birthDetails ? (
            <button
              className={styles.birthBadge}
              onClick={() => setShowBirthForm(true)}
              title="Edit birth details"
            >
              <Star size={12} />
              <span>{birthDetails.name || birthDetails.place}</span>
            </button>
          ) : (
            <button
              className={styles.birthBtn}
              onClick={() => setShowBirthForm(true)}
            >
              + Add birth details
            </button>
          )}

          {messages.length > 0 && (
            <button
              className={styles.iconBtn}
              onClick={clearMessages}
              title="Clear conversation"
            >
              <RefreshCw size={14} />
            </button>
          )}
        </div>
      </header>

      {/* Messages area */}
      <main className={styles.main}>
        {isEmpty ? (
          <div className={styles.welcome}>
            <div className={styles.welcomeSymbol}>✦</div>
            <h1 className={styles.welcomeTitle}>Welcome to Aradhana</h1>
            <p className={styles.welcomeSubtitle}>
              Your daily astrological companion — share your birth details and ask anything about your chart, the stars, or today's energy.
            </p>

            {!birthDetails && (
              <button className={styles.welcomeFormBtn} onClick={() => setShowBirthForm(true)}>
                Begin with your birth details
              </button>
            )}

            <div className={styles.suggestions}>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className={styles.suggestion}
                  onClick={() => { setInput(s); inputRef.current?.focus() }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className={styles.messages}>
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      {/* Error bar */}
      {error && (
        <div className={styles.errorBar}>
          <AlertCircle size={14} />
          <span>{error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Input bar */}
      <footer className={styles.footer}>
        <div className={styles.inputRow}>
          <textarea
            ref={inputRef}
            className={styles.textarea}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={birthDetails
              ? "Ask about your chart, transits, or any astrological question…"
              : "Ask anything — or add your birth details for a personal reading…"}
            rows={1}
            disabled={isStreaming}
          />
          <button
            className={styles.sendBtn}
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
          >
            <Send size={16} />
          </button>
        </div>
        <p className={styles.disclaimer}>
          Aradhana offers guidance for reflection only — not medical, legal, or financial advice.
        </p>
      </footer>

      {/* Birth form modal */}
      {showBirthForm && <BirthForm onClose={() => setShowBirthForm(false)} />}
    </div>
  )
}
