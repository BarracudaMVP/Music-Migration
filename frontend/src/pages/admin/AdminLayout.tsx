import { NavLink, Outlet, Link } from 'react-router-dom'

export default function AdminLayout() {
  return (
    <div className="admin-layout">
      <div className="admin-sidebar">
        <div className="admin-sidebar-header">
          <Link to="/" className="admin-back-link">← На сайт</Link>
          <span className="admin-title">Admin</span>
        </div>
        <nav className="admin-nav">
          <NavLink to="/dashboard" className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}>
            Dashboard
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
