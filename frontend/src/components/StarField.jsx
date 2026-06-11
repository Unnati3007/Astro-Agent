import { useEffect, useRef } from 'react'

const STAR_COUNT = 120

function randomStars(count) {
  return Array.from({ length: count }, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    r: Math.random() * 1.2 + 0.3,
    opacity: Math.random() * 0.6 + 0.1,
    duration: Math.random() * 4 + 3,
    delay: Math.random() * 5,
  }))
}

const STARS = randomStars(STAR_COUNT)

export default function StarField() {
  return (
    <svg
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 0,
      }}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <radialGradient id="nebula" cx="60%" cy="30%" r="50%">
          <stop offset="0%" stopColor="#1a1408" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#0a0908" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#nebula)" />
      {STARS.map((s) => (
        <circle
          key={s.id}
          cx={`${s.x}%`}
          cy={`${s.y}%`}
          r={s.r}
          fill="#f0e8c8"
          opacity={s.opacity}
        >
          <animate
            attributeName="opacity"
            values={`${s.opacity};${s.opacity * 0.2};${s.opacity}`}
            dur={`${s.duration}s`}
            begin={`${s.delay}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
    </svg>
  )
}
