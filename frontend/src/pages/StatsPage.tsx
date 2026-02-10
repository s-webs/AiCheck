import { useEffect, useState } from 'react'
import api from '../api/client'
import type { Stats } from '../api/types'

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<Stats>('/stats')
      setStats(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Не удалось загрузить статистику')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div>
      <h1>Статистика</h1>
      <button onClick={load} disabled={loading}>
        Обновить
      </button>
      {error && <p className="error">{error}</p>}
      {stats && (
        <div className="card">
          <p>Всего проверок: {stats.total_checks}</p>
          <p>Всего токенов: {stats.total_tokens}</p>
          <h2>По языкам</h2>
          <ul>
            {Object.entries(stats.by_language).map(([lang, count]) => (
              <li key={lang}>
                {lang}: {count}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

