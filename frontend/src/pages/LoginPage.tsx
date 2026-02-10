import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await api.post('/auth/login', { username, password })
      const token: string | undefined = res.data?.access_token
      if (token) {
        localStorage.setItem('aicheck_token', token)
        navigate('/', { replace: true })
      } else {
        setError('Не удалось получить токен')
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Ошибка входа')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-root">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>AiCheck — вход</h1>
        <label>
          Логин
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label>
          Пароль
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={loading}>
          {loading ? 'Вход...' : 'Войти'}
        </button>
      </form>
    </div>
  )
}

