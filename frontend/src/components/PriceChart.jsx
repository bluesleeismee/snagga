import React from 'react'
import { fmtPriceShort, chartStatus } from '../utils.js'

export default function PriceChart({ prices, avgPrice, allTimeLow, asin = 'c' }) {
  if (!prices || prices.length < 2) return null

  const W = 300, H = 78
  const PAD_L = 38, PAD_R = 4, PAD_T = 6, PAD_B = 18
  const chartW = W - PAD_L - PAD_R
  const chartH = H - PAD_T - PAD_B

  const minVal = Math.min(...prices)
  const maxVal = Math.max(...prices)
  const padding = (maxVal - minVal) * 0.08 || maxVal * 0.05
  const yMin = Math.max(0, minVal - padding)
  const yMax = maxVal + padding
  const range = yMax - yMin || 1

  const toX = i => PAD_L + (i / (prices.length - 1)) * chartW
  const toY = p => PAD_T + chartH - ((p - yMin) / range) * chartH

  const pts = prices.map((p, i) => ({ x: toX(i), y: toY(p) }))
  const pathD = pts.map((pt, i) => `${i === 0 ? 'M' : 'L'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ')
  const fillD = pathD
    + ` L${pts[pts.length - 1].x.toFixed(1)},${(PAD_T + chartH).toFixed(1)}`
    + ` L${PAD_L},${(PAD_T + chartH).toFixed(1)} Z`

  const currentX = pts[pts.length - 1].x
  const currentY = pts[pts.length - 1].y
  const avgY = avgPrice ? toY(Math.min(Math.max(avgPrice, yMin), yMax)) : null

  const yLabelTop = yMax
  const yLabelMid = (yMax + yMin) / 2
  const yLabelBot = yMin

  const gradId = `cf_${asin}`
  const status = chartStatus(prices, avgPrice, allTimeLow)

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <span style={{ fontSize: 10, color: 'var(--muted)' }}>Preis · 90 Tage</span>
        {status && (
          <span style={{ fontSize: 10, fontWeight: 600, color: status.color }}>{status.text}</span>
        )}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', overflow: 'visible' }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#E8500A" stopOpacity="0.13" />
            <stop offset="100%" stopColor="#E8500A" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        <line x1={PAD_L} y1={PAD_T}              x2={W - PAD_R} y2={PAD_T}              stroke="var(--border)" strokeWidth="0.8" />
        <line x1={PAD_L} y1={PAD_T + chartH / 2} x2={W - PAD_R} y2={PAD_T + chartH / 2} stroke="var(--border)" strokeWidth="0.8" />
        <line x1={PAD_L} y1={PAD_T + chartH}     x2={W - PAD_R} y2={PAD_T + chartH}     stroke="var(--border)" strokeWidth="0.8" />

        {/* Y-axis labels */}
        <text x={PAD_L - 4} y={PAD_T + 4}              textAnchor="end" fontSize="10" fill="var(--text)" fontFamily="inherit">{fmtPriceShort(yLabelTop)}</text>
        <text x={PAD_L - 4} y={PAD_T + chartH / 2 + 4} textAnchor="end" fontSize="10" fill="var(--text)" fontFamily="inherit">{fmtPriceShort(yLabelMid)}</text>
        <text x={PAD_L - 4} y={PAD_T + chartH + 4}     textAnchor="end" fontSize="10" fill="var(--text)" fontFamily="inherit">{fmtPriceShort(yLabelBot)}</text>

        {/* Average dashed line */}
        {avgY !== null && (
          <line x1={PAD_L} y1={avgY} x2={W - PAD_R} y2={avgY}
            stroke="var(--border)" strokeWidth="1.2" strokeDasharray="4,3" />
        )}

        {/* Fill */}
        <path d={fillD} fill={`url(#${gradId})`} />

        {/* Price line */}
        <path d={pathD} fill="none" stroke="#E8500A" strokeWidth="1.8"
          strokeLinejoin="round" strokeLinecap="round" />

        {/* Current price dot */}
        <circle cx={currentX} cy={currentY} r="3" fill="#E8500A" />

        {/* X-axis labels */}
        <text x={PAD_L}     y={H - 2} textAnchor="start" fontSize="10" fill="var(--text)" fontFamily="inherit">–90 Tage</text>
        <text x={W - PAD_R} y={H - 2} textAnchor="end"   fontSize="10" fill="var(--text)" fontFamily="inherit">heute</text>
      </svg>
    </div>
  )
}
