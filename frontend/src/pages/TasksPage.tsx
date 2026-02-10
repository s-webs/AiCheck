import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import type { Task } from '../api/types'

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<Task[]>('/tasks')
      setTasks(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Не удалось загрузить задачи')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div>
      <h1>Проверки</h1>
      <button onClick={load} disabled={loading}>
        Обновить
      </button>
      {error && <p className="error">{error}</p>}
      <div className="table">
        <div className="table-header">
          <span>ID</span>
          <span>Дата</span>
          <span>Статус</span>
          <span>Язык</span>
          <span>Риск</span>
          <span>Файл</span>
          <span>Действия</span>
        </div>
        {tasks.map((t) => (
          <div key={t.id} className="table-row">
            <span>#{t.id}</span>
            <span>{t.created_at?.slice(0, 19)}</span>
            <span>{t.status}</span>
            <span>{t.detected_language ?? '—'}</span>
            <span>{t.risk_level ?? '—'}</span>
            <span>{t.file_name ?? '—'}</span>
            <span>
              {t.result_id && (
                <button onClick={() => navigate(`/results/${t.result_id}`)}>Открыть</button>
              )}
              {t.status === 'error' && t.error_message && <span>{t.error_message}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

