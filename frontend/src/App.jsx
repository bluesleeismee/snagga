import React, { useState } from 'react'
import DealsPage from './pages/DealsPage.jsx'
import LegalPage from './pages/LegalPage.jsx'

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
        <DealsPage />
      ) : path === '/legal' ? (
        <LegalPage />
      ) : (
        <NotFoundPage />
      )}
    </div>
  )
}
