const BASE = import.meta.env.VITE_API_URL || '/api'

export async function streamChat({ message, sessionId, birthDetails, onToken, onToolCall, onDone, onError }) {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId || '',
      birth_details: birthDetails || null,
    }),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API error ${res.status}: ${text}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const eventMatch = part.match(/^event:\s*(\S+)/)
      const dataMatch = part.match(/^data:\s*(.+)/m)
      if (!dataMatch) continue

      const eventType = eventMatch?.[1] || 'message'
      let data
      try { data = JSON.parse(dataMatch[1]) } catch { continue }

      switch (eventType) {
        case 'token':
          onToken?.(data.text || '')
          break
        case 'tool_call':
          onToolCall?.(data)
          break
        case 'done':
          onDone?.(data)
          break
        case 'error':
          onError?.(data.message || 'Unknown error')
          break
      }
    }
  }
}

export async function saveBirthDetails({ sessionId, date, time, place, name }) {
  const res = await fetch(`${BASE}/session/birth`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, date, time, place, name }),
  })
  if (!res.ok) throw new Error('Failed to save birth details')
  return res.json()
}

export async function healthCheck() {
  const res = await fetch(`${BASE}/health`)
  return res.ok
}
