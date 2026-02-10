import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { ResultSummary } from '../api/types'

export default function HistoryPage() {
  const [items, setItems] = useState<ResultSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<ResultSummary[]>('/results')
      setItems(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Не удалось загрузить историю')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div>
      <h1>История проверок</h1>
      <button onClick={load} disabled={loading}>
        Обновить
      </button>
      {error && <p className="error">{error}</p>}
      <div className="table">
        <div className="table-header">
          <span>Дата</span>
          <span>Файл</span>
          <span>Язык</span>
          <span>Риск</span>
          <span>Токенов</span>
          <span>Действия</span>
        </div>
        {items.map((r) => (
          <div key={r.id} className="table-row">
            <span>{r.created_at?.slice(0, 19)}</span>
            <span>{r.file_name ?? '—'}</span>
            <span>{r.detected_language}</span>
            <span>{r.risk_level}</span>
            <span>{r.total_tokens}</span>
            <span>
              <button onClick={() => navigate(`/results/${r.id}`)}>Открыть</button>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

