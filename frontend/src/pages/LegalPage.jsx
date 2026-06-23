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
            Snagga ist Teilnehmer am Partnerprogramm von Amazon Europe S.à r.l. und Partner des
            Werbeprogramms, das zur Bereitstellung eines Mediums für Websites konzipiert wurde,
            mittels dessen durch die Platzierung von Werbeanzeigen und Links zu amazon.de
            Werbekostenerstattungen verdient werden können. Als Amazon-Partner verdiene ich an
            qualifizierten Käufen eine Provision — für dich entstehen keine Mehrkosten.
            Affiliate-Tag: <strong>snagga-21</strong>
          </p>
        </Section>

        {/* Impressum */}
        <Section title="Impressum">
          <div style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.9 }}>
            <p style={{ margin: 0 }}>
              <strong>Verantwortlich für den Inhalt:</strong><br />
              David Pauli<br />
              Hohfurenstrasse 1<br />
              8610 Uster<br />
              Schweiz<br />
              <a href="mailto:contact@snagga.de" style={{ color: 'var(--blue)' }}>contact@snagga.de</a>
            </p>
            <p style={{ marginTop: 12, color: 'var(--muted)', fontSize: 13, lineHeight: 1.6 }}>
              Snagga ist ein unabhängiges Privatprojekt und steht in keiner direkten Verbindung
              zu Amazon. Wir sind Teilnehmer am Amazon Partnerprogramm (Partner-Tag: snagga-21).
            </p>
          </div>
        </Section>

        {/* Datenschutz */}
        <Section title="Datenschutzerklärung">
          <div style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.6, display: 'flex', flexDirection: 'column', gap: 14 }}>

            <div>
              <strong>Verantwortlicher</strong><br />
              David Pauli, Hohfurenstrasse 1, 8610 Uster, Schweiz<br />
              <a href="mailto:contact@snagga.de" style={{ color: 'var(--blue)' }}>contact@snagga.de</a>
            </div>

            <div>
              <strong>Keine Erhebung persönlicher Daten</strong><br />
              Snagga erhebt und speichert keine personenbezogenen Daten. Deine Einstellungen
              (Watchlist, Theme) werden ausschliesslich lokal auf deinem Gerät gespeichert
              (localStorage) und nie an Server übertragen.
            </div>

            <div>
              <strong>Hosting & Server-Logs</strong><br />
              Diese Website wird über Vercel (Frontend) und Render (Backend, USA) gehostet.
              Beim Aufruf werden technisch bedingt IP-Adressen kurzzeitig in Server-Logs
              gespeichert und danach automatisch gelöscht. Es gelten die Datenschutzrichtlinien
              von <a href="https://vercel.com/legal/privacy-policy" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)' }}>Vercel</a> und{' '}
              <a href="https://render.com/privacy" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)' }}>Render</a>.
              Beide Anbieter sind nach EU-Standardvertragsklauseln (SCCs) zertifiziert.
            </div>

            <div>
              <strong>Preisdaten</strong><br />
              Preisdaten werden von CamelCamelCamel-RSS-Feeds und der Amazon Product
              Advertising API bezogen. Es werden keine Nutzerdaten an Dritte weitergegeben.
            </div>

            <div>
              <strong>Affiliate-Links</strong><br />
              Affiliate-Links führen zu Amazon.de. Dort gelten die{' '}
              <a href="https://www.amazon.de/gp/help/customer/display.html?nodeId=GX7NJQ4ZB8MHFRNJ" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)' }}>Datenschutzbestimmungen von Amazon</a>.
              Amazon setzt ggf. Cookies zur Nachverfolgung von Affiliate-Verkäufen.
            </div>

            <div>
              <strong>Deine Rechte</strong><br />
              Du hast das Recht auf Auskunft, Berichtigung, Löschung und Widerspruch
              (Art. 15–21 DSGVO; Art. 25, 28 DSG CH). Da wir keine personenbezogenen
              Daten speichern, ist eine Ausübung dieser Rechte typischerweise nicht
              erforderlich. Bei Fragen wende dich an{' '}
              <a href="mailto:contact@snagga.de" style={{ color: 'var(--blue)' }}>contact@snagga.de</a>.
            </div>

            <div>
              <strong>Aufsichtsbehörden</strong><br />
              Schweiz: <a href="https://www.edoeb.admin.ch" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)' }}>EDÖB</a> — Eidgenössischer Datenschutz- und Öffentlichkeitsbeauftragter<br />
              Deutschland: <a href="https://www.bfdi.bund.de" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)' }}>BfDI</a> — Bundesbeauftragte für den Datenschutz und die Informationsfreiheit
            </div>

            <p style={{ margin: 0, fontSize: 12, color: 'var(--muted)' }}>
              Stand: Juni 2026 · Es gilt das Schweizer DSG sowie die DSGVO (EU) 2016/679.
            </p>
          </div>
        </Section>

        {/* Preisangaben */}
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
