import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

const primaryLinks = [
  { to: '/', label: 'Home', end: true },
  { to: '/products', label: 'Products', end: false },
  { to: '/about', label: 'About Us', end: false },
]

export default function NavBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/')
  }

  return (
    <header className="nav">
      <div className="nav__inner">
        <NavLink to="/" className="nav__brand">
          <span className="nav__brand-mark">CC</span>
          <span className="nav__brand-text">
            <strong>Campus Customs</strong>
            <small>New Haven, CT</small>
          </span>
        </NavLink>

        <nav className="nav__links" aria-label="Primary">
          {primaryLinks.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) => (isActive ? 'nav__link nav__link--active' : 'nav__link')}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="nav__account">
          {user ? (
            <>
              <span className="nav__user">
                Hi, {user.first_name ?? user.name.split(' ')[0]}
              </span>
              <button type="button" className="nav__logout" onClick={handleLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink
                to="/login"
                className={({ isActive }) => (isActive ? 'nav__link nav__link--active' : 'nav__link')}
              >
                Log in
              </NavLink>
              <NavLink to="/create-account" className="nav__cta">
                Create account
              </NavLink>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
