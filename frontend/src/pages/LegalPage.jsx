import React, { useEffect } from 'react'

export default function LegalPage() {
  useEffect(() => {
    const hash = window.location.hash
    if (hash) {
      setTimeout(() => {
        const el = document.querySelector(hash)
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 100)
    }
  }, [])

  return (
    <div style={{ minHeight: '100%', background: 'var(--bg)' }}>

      {/* Header */}
      <header style={{ background: '#153D68', borderBottom: '1px solid #1E5080', position: 'sticky', top: 0, zIndex: 100, height: 72, display: 'flex', alignItems: 'center' }}>
        <div style={{ maxWidth: 1840, width: '98%', margin: '0 auto', display: 'flex', alignItems: 'center', gap: 24 }}>
          <a href="/" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.5px', color: '#EDE9E3' }}>
            snagga<span style={{ color: '#D4694A' }}>.de</span>
          </a>
          <a href="/" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'rgba(255,255,255,0.7)', marginLeft: 16, transition: 'color 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.color = '#fff'}
            onMouseLeave={e => e.currentTarget.style.color = 'rgba(255,255,255,0.7)'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15,18 9,12 15,6"/>
            </svg>
            Zurück zu den Deals
          </a>
        </div>
      </header>

      {/* Content */}
      <main style={{ maxWidth: 860, width: '94%', margin: '0 auto', padding: '56px 0 80px' }}>
        <h1 style={{ fontSize: 36, fontWeight: 800, letterSpacing: '-0.5px', marginBottom: 8, color: 'var(--text)' }}>Rechtliches</h1>
        <p style={{ fontSize: 14, color: 'var(--muted)', marginBottom: 52 }}>snagga.de · Stand: Juni 2026</p>

        <Section id="affiliate" title="Affiliate-Hinweis">
          <p>
            snagga.de ist Teilnehmer am Partnerprogramm von Amazon Europe S.à r.l. und Partner des Werbeprogramms,
            das zur Bereitstellung eines Mediums für Websites konzipiert wurde, mittels dessen durch die Platzierung
            von Werbeanzeigen und Links zu amazon.de Werbekostenerstattungen verdient werden können.
          </p>
          <p>
            Als Amazon-Partner verdienen wir an qualifizierten Käufen eine Provision — für dich entstehen
            dabei <strong>keine zusätzlichen Kosten</strong>. Der angezeigte Preis entspricht dem regulären
            Amazon-Preis.
          </p>
          <p style={{ marginBottom: 0 }}>Amazon-Partner-Tag: <strong>snagga-21</strong></p>
        </Section>

        <Section id="datenschutz" title="Datenschutzerklärung">
          <SubSection title="Verantwortlicher">
            David Pauli, Hohfurenstrasse 1, 8610 Uster, Schweiz ·{' '}
            <a href="mailto:contact@snagga.de" style={{ color: 'var(--accent)' }}>contact@snagga.de</a>
          </SubSection>

          <SubSection title="Keine Erhebung persönlicher Daten">
            snagga.de erhebt und speichert keine personenbezogenen Daten. Deine Einstellungen
            (Theme) werden ausschliesslich lokal auf deinem Gerät gespeichert (localStorage)
            und nie an Server übertragen.
          </SubSection>

          <SubSection title="Hosting & Server-Logs">
            Diese Website wird über Vercel (Frontend) und Render (Backend, USA) gehostet.
            Beim Aufruf werden technisch bedingt IP-Adressen kurzzeitig in Server-Logs erfasst
            und danach automatisch gelöscht. Es gelten die Datenschutzrichtlinien von{' '}
            <a href="https://vercel.com/legal/privacy-policy" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>Vercel</a>{' '}
            und <a href="https://render.com/privacy" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>Render</a>.
            Beide Anbieter sind nach EU-Standardvertragsklauseln (SCCs) zertifiziert.
          </SubSection>

          <SubSection title="Preisdaten">
            Preisdaten werden von CamelCamelCamel-RSS-Feeds bezogen.
            Es werden keine Nutzerdaten an Dritte weitergegeben.
          </SubSection>

          <SubSection title="Affiliate-Links">
            Affiliate-Links führen zu Amazon.de. Dort gelten die{' '}
            <a href="https://www.amazon.de/gp/help/customer/display.html?nodeId=GX7NJQ4ZB8MHFRNJ" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
              Datenschutzbestimmungen von Amazon
            </a>.
            Amazon setzt ggf. Cookies zur Nachverfolgung von Affiliate-Verkäufen.
          </SubSection>

          <SubSection title="Deine Rechte">
            Du hast das Recht auf Auskunft, Berichtigung, Löschung und Widerspruch
            (Art. 15–21 DSGVO; Art. 25, 28 DSG CH). Da wir keine personenbezogenen Daten
            speichern, ist eine Ausübung dieser Rechte typischerweise nicht erforderlich.
            Bei Fragen wende dich an{' '}
            <a href="mailto:contact@snagga.de" style={{ color: 'var(--accent)' }}>contact@snagga.de</a>.
          </SubSection>

          <SubSection title="Aufsichtsbehörden" last>
            Schweiz:{' '}
            <a href="https://www.edoeb.admin.ch" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>EDÖB</a>
            {' '}— Eidgenössischer Datenschutz- und Öffentlichkeitsbeauftragter<br />
            Deutschland:{' '}
            <a href="https://www.bfdi.bund.de" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>BfDI</a>
            {' '}— Bundesbeauftragte für den Datenschutz und die Informationsfreiheit
          </SubSection>
        </Section>

        <Section id="preise" title="Preisangaben">
          <p style={{ marginBottom: 0 }}>
            Alle Preise sind unverbindliche Richtwerte und können sich jederzeit ändern.
            Massgeblich ist der zum Kaufzeitpunkt auf Amazon.de angezeigte Preis.
            snagga.de übernimmt keine Gewähr für die Richtigkeit der Preisangaben.
          </p>
        </Section>

        <Section id="impressum" title="Impressum">
          <p><strong>Verantwortlich für den Inhalt:</strong></p>
          <p>
            David Pauli<br />
            Hohfurenstrasse 1<br />
            8610 Uster<br />
            Schweiz
          </p>
          <p>
            E-Mail: <a href="mailto:contact@snagga.de" style={{ color: 'var(--accent)' }}>contact@snagga.de</a>
          </p>
          <p style={{ marginBottom: 0, color: 'var(--muted)', fontSize: 13 }}>
            snagga.de ist ein unabhängiges Privatprojekt und steht in keiner direkten Verbindung zu Amazon.
            Wir sind Teilnehmer am Amazon-Partnerprogramm (Partner-Tag: snagga-21).
          </p>
        </Section>
      </main>

      {/* Footer */}
      <footer style={{ background: '#153D68', borderTop: '1px solid #1E5080', padding: '24px 2%', textAlign: 'center' }}>
        <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>
          © 2026 snagga.de · <a href="/" style={{ color: 'rgba(255,255,255,0.6)' }}>Zurück zu den Deals</a>
        </p>
      </footer>
    </div>
  )
}

function Section({ id, title, children }) {
  return (
    <section id={id} style={{ marginBottom: 48, scrollMarginTop: 90 }}>
      <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 20, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
        {title}
      </h2>
      <div style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.75, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {children}
      </div>
    </section>
  )
}

function SubSection({ title, children, last }) {
  return (
    <div style={{ paddingBottom: last ? 0 : 14, borderBottom: last ? 'none' : '1px solid var(--border)', marginBottom: last ? 0 : 14 }}>
      <strong style={{ display: 'block', marginBottom: 4, color: 'var(--text)' }}>{title}</strong>
      <span style={{ color: 'var(--muted)', fontSize: 13, lineHeight: 1.7 }}>{children}</span>
    </div>
  )
}
