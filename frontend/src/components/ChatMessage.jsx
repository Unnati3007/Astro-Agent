import ToolActivity from './ToolActivity'
import styles from './ChatMessage.module.css'

const ZODIAC_SYMBOL = '✦'

export default function ChatMessage({ message }) {
  const { role, content, toolEvents, isStreaming } = message

  if (role === 'system') {
    return (
      <div className={styles.system}>
        <span>{ZODIAC_SYMBOL}</span>
        <span>{content}</span>
      </div>
    )
  }

  if (role === 'user') {
    return (
      <div className={styles.userRow}>
        <div className={styles.userBubble}>{content}</div>
      </div>
    )
  }

  // assistant
  return (
    <div className={styles.assistantRow}>
      <div className={styles.avatar}>{ZODIAC_SYMBOL}</div>
      <div className={styles.assistantContent}>
        {toolEvents?.length > 0 && <ToolActivity events={toolEvents} />}
        <div className={styles.assistantText}>
          {content ? (
            <FormattedText text={content} />
          ) : (
            <ThinkingDots />
          )}
          {isStreaming && <span className={styles.cursor} />}
        </div>
      </div>
    </div>
  )
}

function FormattedText({ text }) {
  // Simple paragraph rendering — split on double newlines
  const paragraphs = text.split(/\n\n+/)
  return (
    <>
      {paragraphs.map((p, i) => {
        if (p.trim().startsWith('•') || p.trim().startsWith('-')) {
          // Render as list
          const items = p.split('\n').filter(Boolean)
          return (
            <ul key={i} className={styles.list}>
              {items.map((item, j) => (
                <li key={j}>{item.replace(/^[•\-]\s*/, '')}</li>
              ))}
            </ul>
          )
        }
        return <p key={i}>{p}</p>
      })}
    </>
  )
}

function ThinkingDots() {
  return (
    <span className={styles.thinking}>
      <span />
      <span />
      <span />
    </span>
  )
}
