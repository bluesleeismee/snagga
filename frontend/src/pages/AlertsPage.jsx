import React, { useState } from 'react'
import { fmtPrice } from '../utils.js'

export default function AlertsPage({ alerts, onAddAlert, onRemoveAlert, onToggleAlert, theme, onToggleTheme }) {
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ name: '', asin: '', targetPrice: '' })

  function handleAdd(e) {
    e.preventDefault()
    if (!form.name || !form.targetPrice) return
    onAddAlert({
      id: Date.now(),
      name: form.name,
      asin: form.asin,
      targetPrice: parseFloat(form.targetPrice),
      currentPrice: parseFloat(form.targetPrice) * 1.15,
      enabled: true,
    })
    setForm({ name: '', asin: '', targetPrice: '' })
    setShowAdd(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ position: 'sticky', top: 0, zIndex: 6, background: 'var(--bg)', padding: '18px 16px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 21, letterSpacing: '-.3px' }}>Preis-Alerts</span>
        <button onClick={onToggleTheme} style={{ width: 36, height: 36, borderRadius: 9, border: '1px solid var(--border)', background: 'var(--bg-elev2)', color: 'var(--text)', fontSize: 15, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </div>

      <div className="no-scroll" style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Neuen Alert anlegen */}
        <button
          onClick={() => setShowAdd(v => !v)}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            width: '100%', padding: 13, borderRadius: 12,
            border: '1.5px dashed var(--border)', background: 'var(--bg-elev)',
            color: 'var(--cyan)', fontWeight: 700, fontSize: 14,
          }}
        >
          <span style={{ fontSize: 17 }}>+</span> Neuer Alert
        </button>

        {/* Add-Formular */}
        {showAdd && (
          <form
            onSubmit={handleAdd}
            style={{ background: 'var(--bg-elev)', border: '1px solid var(--border)', borderRadius: 14, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}
          >
            <span style={{ fontFamily: 'Space Grotesk', fontWeight: 600, fontSize: 15 }}>Alert einrichten</span>
            {[
              { key: 'name', label: 'Produktname', placeholder: 'z.B. Sony WH-1000XM5', required: true },
              { key: 'asin', label: 'ASIN (optional)', placeholder: 'z.B. B09XS7JWHH' },
              { key: 'targetPrice', label: 'Zielpreis (€)', placeholder: 'z.B. 199.99', type: 'number', required: true },
            ].map(f => (
              <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 600 }}>{f.label}</label>
                <input
                  value={form[f.key]}
                  onChange={e => setForm(v => ({ ...v, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  type={f.type || 'text'}
                  required={f.required}
                  step={f.type === 'number' ? '0.01' : undefined}
                  style={{ padding: '10px 12px', borderRadius: 9, border: '1px solid var(--border)', background: 'var(--bg-elev2)', color: 'var(--text)', fontSize: 14, outline: 'none' }}
                />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" onClick={() => setShowAdd(false)} style={{ flex: 1, padding: '10px', borderRadius: 9, border: '1px solid var(--border)', background: 'var(--bg-elev2)', color: 'var(--muted)', fontWeight: 600, fontSize: 13 }}>
                Abbrechen
              </button>
              <button type="submit" style={{ flex: 2, padding: '10px', borderRadius: 9, border: 'none', background: 'var(--red)', color: '#fff', fontWeight: 700, fontSize: 13 }}>
                Alert speichern
              </button>
            </div>
          </form>
        )}

        {/* Alert-Liste */}
        {alerts.length === 0 && !showAdd && (
          <div style={{ textAlign: 'center', padding: '50px 20px', color: 'var(--muted)', fontSize: 14 }}>
            Keine aktiven Alerts. Lege oben einen an.
          </div>
        )}

        {alerts.map(a => {
          const reached = a.currentPrice <= a.targetPrice
          return (
            <div
              key={a.id}
              style={{ background: 'var(--bg-elev)', border: '1px solid var(--border)', borderRadius: 14, padding: 14, display: 'flex', alignItems: 'center', gap: 12 }}
            >
              <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ fontFamily: 'Space Grotesk', fontWeight: 600, fontSize: 14, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {a.name}
                </div>
                <div style={{ display: 'flex', gap: 14, fontSize: 12 }}>
                  <span style={{ color: 'var(--muted)' }}>
                    Ziel <span style={{ color: 'var(--cyan)', fontWeight: 700, fontFamily: 'Space Grotesk' }}>{fmtPrice(a.targetPrice)}</span>
                  </span>
                </div>
                <div style={{ fontSize: 11, fontWeight: 700, color: reached ? 'var(--green)' : 'var(--yellow)' }}>
                  {reached ? '✓ Zielpreis erreicht!' : '⏳ Warten auf Preissenkung'}
                </div>
              </div>

              {/* Toggle */}
              <button
                onClick={() => onToggleAlert(a.id)}
                style={{
                  flexShrink: 0, width: 44, height: 26, borderRadius: 99, border: 'none', padding: 0, position: 'relative',
                  background: a.enabled ? 'var(--red)' : 'var(--bg-elev2)',
                  transition: 'background .15s',
                }}
              >
                <span style={{
                  position: 'absolute', top: 3, left: a.enabled ? 21 : 3,
                  width: 20, height: 20, borderRadius: '50%',
                  background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.4)',
                  transition: 'left .15s',
                }} />
              </button>

              {/* Löschen */}
              <button
                onClick={() => onRemoveAlert(a.id)}
                style={{ flexShrink: 0, width: 30, height: 30, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-elev2)', color: 'var(--muted)', fontSize: 16, lineHeight: 1, padding: 0 }}
              >
                ×
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
