import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const useStore = create(
  persist(
    (set, get) => ({
      // Session
      sessionId: null,
      setSessionId: (id) => set({ sessionId: id }),

      // Birth details
      birthDetails: null,
      setBirthDetails: (details) => set({ birthDetails: details }),
      hasBirthDetails: () => !!get().birthDetails,

      // Chat messages
      messages: [],
      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      updateLastAssistant: (patch) => set((s) => {
        const msgs = [...s.messages]
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'assistant') {
            msgs[i] = { ...msgs[i], ...patch }
            break
          }
        }
        return { messages: msgs }
      }),
      clearMessages: () => set({ messages: [] }),

      // Tool activity log
      toolActivity: [],
      addToolActivity: (event) => set((s) => ({
        toolActivity: [...s.toolActivity, { ...event, ts: Date.now() }]
      })),
      clearToolActivity: () => set({ toolActivity: [] }),

      // UI state
      isStreaming: false,
      setIsStreaming: (v) => set({ isStreaming: v }),

      showBirthForm: false,
      setShowBirthForm: (v) => set({ showBirthForm: v }),
    }),
    {
      name: 'aradhana-store',
      partialize: (s) => ({
        sessionId: s.sessionId,
        birthDetails: s.birthDetails,
        messages: s.messages.slice(-50), // keep last 50
      }),
    }
  )
)

export default useStore
