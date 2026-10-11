import React, { useState, useEffect } from 'react'
import DealsPage from './pages/DealsPage.jsx'
import LegalPage from './pages/LegalPage.jsx'
import PausePage from './pages/PausePage.jsx'
import { api } from './api.js'

// Pausenmodus (11.10.2026): Die Startseite fragt das Backend (/status), ob
// SNAGGA_PAUSED gesetzt ist, und zeigt dann statt der Deals die Pausenseite.
// Ein einziger Schalter in Render steuert so Backend UND Frontend — kein
// zweiter Schalter in Vercel. Schlägt die Abfrage fehl, gilt "nicht pausiert"
// (= bisheriges Verhalten), damit ein Netzproblem die Seite nie lahmlegt.
function HomePage() {
  const [paused, setPaused] = useState(null)
  useEffect(() => {
    api.status()
      .then(s => setPaused(!!(s && s.paused)))
      .catch(() => setPaused(false))
  }, [])
  if (paused === null) return null
  return paused ? <PausePage /> : <DealsPage />
}

function NotFoundPage() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 16, padding: 24, textAlign: 'center', background: 'var(--bg)' }}>
      <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: 80, fontWeight: 400, color: 'var(--accent)', lineHeight: 1 }}>404</div>
      <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--text)' }}>Diese Seite gibt's nicht</div>
      <div style={{ fontSize: 14, color: 'var(--muted)', maxWidth: 300 }}>Aber jede Menge ausgewählte Amazon-Deals schon.</div>
      <a href="/" style={{ marginTop: 8, padding: '12px 28px', background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 14 }}>
        Zurück zu den Deals
      </a>
    </div>
  )
}

export default function App() {
  const path = window.location.pathname

  return (
    <div style={{ minHeight: '100%', background: 'var(--bg)', color: 'var(--text)' }}>
      {path === '/' ? (
        <HomePage />
      ) : path === '/legal' ? (
        <LegalPage />
      ) : (
        <NotFoundPage />
      )}
    </div>
  )
}
