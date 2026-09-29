import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
} from 'react-router-dom'
import { ConsumerSearchPage } from './pages/ConsumerSearchPage'
import { CommunityReportsPage } from './pages/CommunityReportsPage'
import { I18nProvider, useI18n, type Language } from './i18n'

const languages: { code: Language; label: string }[] = [
  { code: 'en', label: 'EN' },
  { code: 'pt-BR', label: 'PT-BR' },
  { code: 'es-419', label: 'ES-LATAM' },
]

function AppContent() {
  const { language, setLanguage, t } = useI18n()
  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="site-header">
          <Link className="brand" to="/" aria-label={t('home')}>
            <img
              className="brand-mark"
              src="/justsupply-logo-no-check-256.png"
              alt=""
              aria-hidden="true"
            />
            <span>JustSupply</span>
          </Link>

          <div className="header-tools">
            <Link className="header-link" to="/community-reports">{t('communityReports')}</Link>
            <span className="environment-badge">{t('appBadge')}</span>
            <div className="language-switcher" role="group" aria-label={t('languageLabel')}>
              {languages.map(({ code, label }) => (
                <button
                  type="button"
                  key={code}
                  className={language === code ? 'active' : ''}
                  aria-pressed={language === code}
                  onClick={() => setLanguage(code)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </header>

        <Routes>
          <Route path="/" element={<ConsumerSearchPage />} />
          <Route path="/community-reports" element={<CommunityReportsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

        <footer>
          <span>JustSupply</span>
          <span>{t('footerTagline')}</span>
        </footer>
      </div>
    </BrowserRouter>
  )
}

function App() {
  return (
    <I18nProvider>
      <AppContent />
    </I18nProvider>
  )
}

export default App
