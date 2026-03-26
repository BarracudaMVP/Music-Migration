import { createContext, useContext, useState } from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import HomePage from './pages/HomePage'
import AuthCallbackPage from './pages/AuthCallbackPage'
import MigratePage from './pages/MigratePage'
import ProgressPage from './pages/ProgressPage'
import HistoryPage from './pages/HistoryPage'
import AdminLayout from './pages/admin/AdminLayout'
import AdminDashboardPage from './pages/admin/AdminDashboardPage'
import AdminMigrationsPage from './pages/admin/AdminMigrationsPage'
import AdminUsersPage from './pages/admin/AdminUsersPage'
import { getTokenRole } from './api/auth'

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
        <Route element={<AdminRoute />}>
          <Route element={<AdminLayout />}>
            <Route path="/dashboard" element={<AdminDashboardPage />} />
            <Route path="/migrations" element={<AdminMigrationsPage />} />
            <Route path="/users" element={<AdminUsersPage />} />
          </Route>
        </Route>
      </Routes>
    </LangContext.Provider>
  )
}

function AdminRoute() {
  if (getTokenRole() !== 'admin') return <Navigate to="/" replace />
  return <Outlet />
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
