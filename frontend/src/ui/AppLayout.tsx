import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'

const navItems = [
  { to: '/checks/new', label: 'Новая проверка' },
  { to: '/checks', label: 'Проверки' },
  { to: '/history', label: 'История' },
  { to: '/stats', label: 'Статистика' },
  { to: '/prompts', label: 'Промпты' },
]

export default function AppLayout() {
  const navigate = useNavigate()

  useEffect(() => {
    const token = localStorage.getItem('aicheck_token')
    if (!token) {
      navigate('/login', { replace: true })
    }
  }, [navigate])

  const handleLogout = () => {
    localStorage.removeItem('aicheck_token')
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-root">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Link to="/" className="logo">
            AiCheck
          </Link>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button className="logout-btn" onClick={handleLogout}>
          Выйти
        </button>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}

