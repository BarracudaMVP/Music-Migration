import { NavLink, Outlet, Link } from 'react-router-dom'
import { useLang } from '../../App'
import { t } from '../../i18n'

export default function AdminLayout() {
  const { lang } = useLang()
  return (
    <div className="admin-layout">
      <div className="admin-sidebar">
        <div className="admin-sidebar-header">
          <Link to="/" className="admin-back-link">{t('back_to_site', lang)}</Link>
          <span className="admin-title">Admin</span>
        </div>
        <nav className="admin-nav">
          <NavLink to="/dashboard" className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}>
            {t('dashboard', lang)}
          </NavLink>
          <NavLink to="/migrations" className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}>
            Migrations
          </NavLink>
          <NavLink to="/users" className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}>
            Users
          </NavLink>
        </nav>
      </div>
      <div className="admin-content">
        <Outlet />
      </div>
    </div>
  )
}
