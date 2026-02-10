import { type FormEvent, useEffect, useState } from 'react'
import api from '../api/client'
import type { Prompts } from '../api/types'

export default function PromptsPage() {
  const [systemMessage, setSystemMessage] = useState('')
  const [userTemplate, setUserTemplate] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setMessage(null)
    try {
      const res = await api.get<Prompts>('/prompts')
      setSystemMessage(res.data.system_message)
      setUserTemplate(res.data.user_message_template)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail ?? 'Не удалось загрузить промпты')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setMessage(null)
    try {
      const res = await api.put<Prompts>('/prompts', {
        system_message: systemMessage,
        user_message_template: userTemplate,
      })
      setSystemMessage(res.data.system_message)
      setUserTemplate(res.data.user_message_template)
      setMessage('Промпты сохранены')
    } catch (err: any) {
      setMessage(err?.response?.data?.detail ?? 'Ошибка сохранения промптов')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <h1>Промпты</h1>
      {loading && <p>Загрузка...</p>}
      {message && <p>{message}</p>}
      <form className="card vertical" onSubmit={handleSubmit}>
        <label>
          System message
          <textarea
            value={systemMessage}
            onChange={(e) => setSystemMessage(e.target.value)}
            rows={8}
          />
        </label>
        <label>
          User message template
          <textarea
            value={userTemplate}
            onChange={(e) => setUserTemplate(e.target.value)}
            rows={10}
          />
        </label>
        <button type="submit" disabled={saving}>
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      </form>
    </div>
  )
}

