import React, { useEffect } from 'react'

// Pausenseite (11.10.2026) — erscheint auf der Startseite, solange das
// Backend mit SNAGGA_PAUSED läuft. Keine Preise, keine Deals: lieber gar kein
// Preis als ein veralteter. Gegenstück zur SSR-Pausenseite in backend/main.py.
export default function PausePage() {
  useEffect(() => {
    document.title = 'snagga macht gerade Pause'
  }, [])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <header style={{ background: '#153D68', height: 72, display: 'flex', alignItems: 'center', padding: '0 18px' }}>
        <a href="/" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", fontSize: 26, fontWeight: 800, letterSpacing: '-0.5px', color: '#EDE9E3' }}>
          snagga<span style={{ color: '#C85E43' }}>.de</span>
        </a>
      </header>
      <main style={{ flex: 1, maxWidth: 620, width: '90%', margin: '0 auto', padding: '64px 0 80px' }}>
        <h1 style={{ fontSize: 30, lineHeight: 1.25, margin: '0 0 16px', color: 'var(--text)' }}>snagga macht gerade Pause</h1>
        <p style={{ fontSize: 17, lineHeight: 1.65, color: 'var(--text)', margin: '0 0 18px' }}>
          Deals, Preisseiten und der Preis-Check sind im Moment offline. Lieber gar kein Preis
          als ein veralteter — deshalb zeigen wir in dieser Zeit keine Angebote.
        </p>
        <p style={{ fontSize: 17, lineHeight: 1.65, color: 'var(--text)', margin: '0 0 18px' }}>
          Weiterhin lesbar ist unser Ratgeber:{' '}
          <a href="/ratgeber/kaufzeitpunkt" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>
            Wann kauft man am günstigsten?
          </a>
        </p>
        <p style={{ fontSize: 15, color: 'var(--muted)', marginTop: 32 }}>
          <a href="/legal" style={{ color: 'var(--muted)', textDecoration: 'underline' }}>Impressum &amp; Datenschutz</a>
        </p>
      </main>
    </div>
  )
}
