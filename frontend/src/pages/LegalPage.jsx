import React from 'react'

export default function LegalPage({ onBack }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 6,
        background: 'var(--bg)', padding: '18px 16px 14px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <button
          onClick={onBack}
          style={{
            width: 34, height: 34, borderRadius: 9,
            border: '1px solid var(--border)', background: 'var(--bg-elev2)',
            color: 'var(--text)', fontSize: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
          }}
        >
          ←
        </button>
        <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 21, letterSpacing: '-.3px' }}>
          Rechtliches
        </span>
      </div>

      <div className="no-scroll" style={{ flex: 1, overflowY: 'auto', padding: '20px 16px 40px', display: 'flex', flexDirection: 'column', gap: 28 }}>

        {/* Affiliate-Hinweis */}
        <Section title="Affiliate-Hinweis">
          <p style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.6, margin: 0 }}>
            Diese Website enthält Affiliate-Links zu Amazon.de. Als Amazon-Partner verdiene ich an
            qualifizierten Käufen eine kleine Provision — für dich entstehen dabei keine Mehrkosten.
            Die Preise und Verfügbarkeiten werden regelmässig aktualisiert, können aber abweichen.
          </p>
        </Section>

        {/* Impressum */}
        <Section title="Impressum">
          <div style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.8 }}>
            <p style={{ margin: 0 }}>
              <strong>Betreiber:</strong> David P.<br />
              <strong>Land:</strong> Schweiz<br />
              <strong>Kontakt:</strong> <a href="mailto:contact@snagga.de" style={{ color: 'var(--cyan)' }}>contact@snagga.de</a>
            </p>
            <p style={{ marginTop: 12, color: 'var(--muted)', fontSize: 13 }}>
              Snagga ist ein unabhängiges Projekt und steht in keiner direkten Verbindung
              zu Amazon. Wir sind Teilnehmer am Amazon Partnerprogramm (snagga-21).
            </p>
          </div>
        </Section>

        {/* Datenschutz */}
        <Section title="Datenschutz">
          <div style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.6, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <p style={{ margin: 0 }}>
              <strong>Keine persönlichen Daten:</strong> Snagga speichert keine Nutzerdaten.
              Deine Einstellungen (Watchlist, Theme, Kategorien) werden ausschliesslich lokal
              auf deinem Gerät gespeichert (localStorage) und nie an Server übertragen.
            </p>
            <p style={{ margin: 0 }}>
              <strong>Externe Links:</strong> Affiliate-Links führen zu Amazon.de.
              Dort gelten die Datenschutzbestimmungen von Amazon.
            </p>
            <p style={{ margin: 0 }}>
              <strong>Hosting & Server-Logs:</strong> Diese Website wird über Vercel (Frontend) und
              Render (Backend) gehostet. Beim Aufruf der Website werden technisch bedingt
              IP-Adressen in Server-Logs gespeichert. Diese Logs werden nicht ausgewertet
              und nach kurzer Zeit automatisch gelöscht. Es gelten die Datenschutzrichtlinien
              von Vercel und Render.
            </p>
            <p style={{ margin: 0 }}>
              <strong>Preisdaten:</strong> Preise werden von CamelCamelCamel RSS-Feeds
              bezogen. Es werden keine Nutzerdaten an Dritte weitergegeben.
            </p>
          </div>
        </Section>

        {/* Amazon Disclaimer */}
        <Section title="Preisangaben">
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, margin: 0 }}>
            Alle Preise sind unverbindliche Richtwerte und können sich jederzeit ändern.
            Massgeblich ist der zum Kaufzeitpunkt auf Amazon.de angezeigte Preis.
            Snagga übernimmt keine Gewähr für die Richtigkeit der Preisangaben.
          </p>
        </Section>

      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.7px', fontWeight: 700 }}>
        {title}
      </span>
      <div style={{ background: 'var(--bg-elev)', border: '1px solid var(--border)', borderRadius: 14, padding: '14px 15px' }}>
        {children}
      </div>
    </div>
  )
}
