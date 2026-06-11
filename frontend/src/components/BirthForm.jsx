import { useState } from 'react'
import { X, Sparkles, MapPin, Calendar, Clock, User } from 'lucide-react'
import useStore from '../lib/store'
import { saveBirthDetails } from '../lib/api'
import styles from './BirthForm.module.css'

export default function BirthForm({ onClose }) {
  const sessionId = useStore((s) => s.sessionId)
  const setBirthDetails = useStore((s) => s.setBirthDetails)
  const addMessage = useStore((s) => s.addMessage)

  const [form, setForm] = useState({
    name: '',
    date: '',
    time: '',
    place: '',
    unknownTime: false,
  })
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }))
    setErrors((er) => ({ ...er, [field]: null }))
  }

  const toggleUnknownTime = () => {
    setForm((f) => ({ ...f, unknownTime: !f.unknownTime, time: !f.unknownTime ? '12:00' : '' }))
  }

  function validate() {
    const errs = {}
    if (!form.date) errs.date = 'Birth date is required'
    else {
      const d = new Date(form.date)
      if (isNaN(d.getTime())) errs.date = 'Enter a valid date'
      else if (d.getFullYear() < 1800 || d.getFullYear() > new Date().getFullYear())
        errs.date = 'Year must be between 1800 and today'
    }
    if (!form.unknownTime && !form.time) errs.time = 'Enter birth time or check "unknown"'
    if (!form.place.trim()) errs.place = 'Birth place is required'
    return errs
  }

  async function handleSubmit() {
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }

    setSaving(true)
    const details = {
      name: form.name.trim() || null,
      date: form.date,
      time: form.unknownTime ? '12:00' : form.time,
      place: form.place.trim(),
    }

    try {
      await saveBirthDetails({ sessionId, ...details })
      setBirthDetails(details)
      addMessage({
        id: Date.now(),
        role: 'system',
        content: `Birth details saved for ${form.name || 'you'} — ${form.date}, ${details.time}, ${form.place}`,
      })
      onClose()
    } catch (err) {
      setErrors({ submit: err.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <Sparkles size={18} className={styles.headerIcon} />
          <h2 className={styles.title}>Your Birth Details</h2>
          <button className={styles.close} onClick={onClose}><X size={16} /></button>
        </div>

        <p className={styles.subtitle}>
          These details allow Aradhana to compute your natal chart with precision.
          Your information is stored only in your browser session.
        </p>

        <div className={styles.fields}>
          <Field label="Your Name (optional)" icon={<User size={14} />} error={errors.name}>
            <input
              className={styles.input}
              type="text"
              placeholder="e.g. Arjun"
              value={form.name}
              onChange={set('name')}
            />
          </Field>

          <Field label="Date of Birth" icon={<Calendar size={14} />} error={errors.date} required>
            <input
              className={styles.input}
              type="date"
              value={form.date}
              onChange={set('date')}
              max={new Date().toISOString().split('T')[0]}
            />
          </Field>

          <Field label="Time of Birth" icon={<Clock size={14} />} error={errors.time} required>
            <div className={styles.timeRow}>
              <input
                className={styles.input}
                type="time"
                value={form.time}
                onChange={set('time')}
                disabled={form.unknownTime}
              />
              <label className={styles.checkLabel}>
                <input
                  type="checkbox"
                  checked={form.unknownTime}
                  onChange={toggleUnknownTime}
                />
                <span>Unknown — use noon</span>
              </label>
            </div>
            {form.unknownTime && (
              <p className={styles.hint}>
                Without an exact birth time, houses and rising sign will be approximate.
              </p>
            )}
          </Field>

          <Field label="Place of Birth" icon={<MapPin size={14} />} error={errors.place} required>
            <input
              className={styles.input}
              type="text"
              placeholder="e.g. New Delhi, India"
              value={form.place}
              onChange={set('place')}
            />
          </Field>
        </div>

        {errors.submit && (
          <p className={styles.submitError}>{errors.submit}</p>
        )}

        <button
          className={styles.submit}
          onClick={handleSubmit}
          disabled={saving}
        >
          {saving ? 'Saving…' : 'Save & Begin Reading'}
        </button>
      </div>
    </div>
  )
}

function Field({ label, icon, error, required, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 12, fontWeight: 500, letterSpacing: '0.06em',
        textTransform: 'uppercase', color: 'var(--text-secondary)',
      }}>
        {icon}
        {label}
        {required && <span style={{ color: 'var(--gold-mid)' }}>*</span>}
      </label>
      {children}
      {error && <span style={{ fontSize: 12, color: 'var(--rose-soft)' }}>{error}</span>}
    </div>
  )
}
