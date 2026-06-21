import React from 'react'
import { miniChart, fmtPrice } from '../utils.js'

export default function PriceChart({ prices, avgPrice, allTimeLow }) {
  const { line, area } = miniChart(prices)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      <svg
        viewBox="0 0 300 54"
        preserveAspectRatio="none"
        style={{ width: '100%', height: 50, display: 'block' }}
      >
        <path d={area} fill="var(--cyan-soft)" stroke="none" />
        <path
          d={line}
          fill="none"
          stroke="var(--cyan)"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
        <span style={{ color: 'var(--muted)' }}>
          Ø 60 T&nbsp;&nbsp;
          <span style={{ color: 'var(--text)', fontWeight: 600, fontFamily: 'Space Grotesk' }}>
            {fmtPrice(avgPrice)}
          </span>
        </span>
        <span style={{ color: 'var(--muted)' }}>
          Allzeit-Tief&nbsp;&nbsp;
          <span style={{ color: 'var(--cyan)', fontWeight: 700, fontFamily: 'Space Grotesk' }}>
            {fmtPrice(allTimeLow)}
          </span>
        </span>
      </div>
    </div>
  )
}
