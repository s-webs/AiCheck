import { type FormEvent, useState } from 'react'
import api from '../api/client'

export default function NewCheckPage() {
  const [file, setFile] = useState<File | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      setMessage('Выберите файл .docx')
      return
    }
    setLoading(true)
    setMessage(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await api.post('/tasks', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setMessage(`Задача #${res.data.id} добавлена в очередь`)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail ?? 'Ошибка при отправке файла')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1>Новая проверка</h1>
      <p>Загрузите файл .docx — проверка будет выполнена в фоне.</p>
      <form onSubmit={handleSubmit} className="card">
        <input
          type="file"
          accept=".docx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Отправка...' : 'Добавить в очередь'}
        </button>
      </form>
      {message && <p>{message}</p>}
    </div>
  )
}

