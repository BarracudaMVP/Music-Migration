import { Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'
import AuthCallbackPage from './pages/AuthCallbackPage'
import MigratePage from './pages/MigratePage'
import ProgressPage from './pages/ProgressPage'
import HistoryPage from './pages/HistoryPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route path="/migrate" element={<MigratePage />} />
      <Route path="/migrate/:id/progress" element={<ProgressPage />} />
      <Route path="/history" element={<HistoryPage />} />
    </Routes>
  )
}
