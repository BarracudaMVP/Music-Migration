import { createContext, useContext, useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'
import AuthCallbackPage from './pages/AuthCallbackPage'
import MigratePage from './pages/MigratePage'
import ProgressPage from './pages/ProgressPage'
import HistoryPage from './pages/HistoryPage'

// ---------------------------------------------------------------------------
// Lang context — shared across all pages
// ---------------------------------------------------------------------------

type Lang = 'ru' | 'en'

interface LangContextValue {
  lang: Lang
  setLang: (l: Lang) => void
}

export const LangContext = createContext<LangContextValue>({
  lang: 'ru',
  setLang: () => {},
})

export function useLang() {
  return useContext(LangContext)
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [lang, setLangState] = useState<Lang>(
    () => (localStorage.getItem('lang') as Lang) ?? 'ru',
  )

  function setLang(l: Lang) {
    setLangState(l)
    localStorage.setItem('lang', l)
  }

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <LangSwitcher lang={lang} setLang={setLang} />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/migrate" element={<MigratePage />} />
        <Route path="/migrate/:id/progress" element={<ProgressPage />} />
        <Route path="/history" element={<HistoryPage />} />
      </Routes>
    </LangContext.Provider>
  )
}

function LangSwitcher({ lang, setLang }: { lang: Lang; setLang: (l: Lang) => void }) {
  return (
    <div className="lang-switcher">
      <button
        className={`lang-btn${lang === 'ru' ? ' active' : ''}`}
        onClick={() => setLang('ru')}
        aria-label="Русский"
      >
        RU
      </button>
      <button
        className={`lang-btn${lang === 'en' ? ' active' : ''}`}
        onClick={() => setLang('en')}
        aria-label="English"
      >
        EN
      </button>
    </div>
  )
}
