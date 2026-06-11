import styles from './ToolActivity.module.css'

const TOOL_LABELS = {
  compute_birth_chart: { label: 'Computing natal chart', icon: '🪐' },
  get_daily_transits:  { label: 'Fetching planetary transits', icon: '✨' },
  geocode_place:       { label: 'Locating birth place', icon: '🌍' },
  knowledge_lookup:    { label: 'Consulting astrology knowledge', icon: '📖' },
}

export default function ToolActivity({ events }) {
  if (!events?.length) return null

  return (
    <div className={styles.container}>
      {events.map((evt, i) => {
        const info = TOOL_LABELS[evt.tool] || { label: evt.tool, icon: '⚙️' }
        return (
          <div key={i} className={styles.event}>
            <span className={styles.icon}>{info.icon}</span>
            <span className={styles.label}>{info.label}</span>
            <span className={styles.done}>✓</span>
          </div>
        )
      })}
    </div>
  )
}
