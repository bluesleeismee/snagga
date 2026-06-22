import React, { useState, useEffect, useCallback } from 'react'
import BottomNav from './components/BottomNav.jsx'
import DealsPage from './pages/DealsPage.jsx'
import WatchlistPage from './pages/WatchlistPage.jsx'
import AlertsPage from './pages/AlertsPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import LegalPage from './pages/LegalPage.jsx'

// ── localStorage helpers ─────────────────────────────────────────────────────
const LS = {
  get: (k, fb) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : fb } catch { return fb } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch {} },
}

export default function App() {
  const [tab, setTab] = useState('deals')

  // Theme
  const [theme, setTheme] = useState(() => LS.get('dr_theme', 'dark'))
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    LS.set('dr_theme', theme)
  }, [theme])

  // Watchlist (Set of ASINs)
  const [watchlist, setWatchlist] = useState(() => new Set(LS.get('dr_watch', [])))
  const toggleWatch = useCallback(asin => {
    setWatchlist(prev => {
      const next = new Set(prev)
      next.has(asin) ? next.delete(asin) : next.add(asin)
      LS.set('dr_watch', [...next])
      return next
    })
  }, [])

  // Alerts
  const [alerts, setAlerts] = useState(() => LS.get('dr_alerts', []))
  useEffect(() => { LS.set('dr_alerts', alerts) }, [alerts])
  const addAlert    = a => setAlerts(v => [a, ...v])
  const removeAlert = id => setAlerts(v => v.filter(a => a.id !== id))
  const toggleAlert = id => setAlerts(v => v.map(a => a.id === id ? { ...a, enabled: !a.enabled } : a))

  // Hidden categories (settings)
  const [hiddenCats, setHiddenCats] = useState(() => new Set(LS.get('dr_hidden_cats', [])))
  const toggleCat = cat => {
    setHiddenCats(prev => {
      const next = new Set(prev)
      next.has(cat) ? next.delete(cat) : next.add(cat)
      LS.set('dr_hidden_cats', [...next])
      return next
    })
  }

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const [showLegal, setShowLegal] = useState(false)

  const sharedProps = { theme, onToggleTheme: toggleTheme }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%', maxWidth: 480, margin: '0 auto',
      background: 'var(--bg)', position: 'relative',
    }}>
      {/* Page */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {showLegal && (
          <LegalPage onBack={() => setShowLegal(false)} />
        )}
        {!showLegal && tab === 'deals' && (
          <DealsPage
            {...sharedProps}
            watchlist={watchlist}
            onToggleWatch={toggleWatch}
          />
        )}
        {!showLegal && tab === 'watchlist' && (
          <WatchlistPage
            {...sharedProps}
            watchlist={watchlist}
            onToggleWatch={toggleWatch}
            onGoDeals={() => setTab('deals')}
          />
        )}
        {!showLegal && tab === 'alerts' && (
          <AlertsPage
            {...sharedProps}
            alerts={alerts}
            onAddAlert={addAlert}
            onRemoveAlert={removeAlert}
            onToggleAlert={toggleAlert}
          />
        )}
        {!showLegal && tab === 'settings' && (
          <SettingsPage
            {...sharedProps}
            onSetTheme={setTheme}
            hiddenCats={hiddenCats}
            onToggleCat={toggleCat}
            onShowLegal={() => setShowLegal(true)}
          />
        )}
      </div>

      {/* Bottom Nav */}
      <BottomNav active={tab} onSelect={setTab} />
    </div>
  )
}
