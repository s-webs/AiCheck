import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import api from '../api/client'
import type { ResultDetail, PdfGenerateResponse } from '../api/types'

export default function ResultPage() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<ResultDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfMessage, setPdfMessage] = useState<string | null>(null)

  const load = async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<ResultDetail>(`/results/${id}`)
      setData(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Не удалось загрузить результат')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  if (!id) {
    return <p>Не указан ID результата.</p>
  }

  if (loading && !data) {
    return <p>Загрузка...</p>
  }

  if (error) {
    return <p className="error">{error}</p>
  }

  if (!data) {
    return <p>Результат не найден.</p>
  }

  const { assessment } = data

  return (
    <div>
      <h1>Результат #{data.id}</h1>
      <p>
        Дата: {data.created_at?.slice(0, 19)} | Язык: {data.detected_language} | Риск:{' '}
        {data.risk_level} | Токенов: {data.total_tokens}
      </p>
      <section className="card">
        <h2>Общая оценка</h2>
        <p>{assessment.overall_assessment}</p>
      </section>
      <section className="card">
        <h2>Уровень риска</h2>
        <p>{assessment.risk_level}</p>
      </section>
      <section className="card">
        <h2>Основные выводы</h2>
        {Array.isArray(assessment.major_findings) &&
          assessment.major_findings.map((f: any, idx: number) => (
            <div key={idx} className="finding">
              <strong>
                [{f.severity}] {f.title}
              </strong>
              <p>{f.details}</p>
            </div>
          ))}
      </section>
      <section className="card">
        <h2>JSON</h2>
        <pre className="json-block">{JSON.stringify(assessment, null, 2)}</pre>
      </section>
      <section className="card">
        <h2>PDF-отчёты</h2>
        <button
          type="button"
          disabled={pdfLoading}
          onClick={async () => {
            if (!id) return
            setPdfLoading(true)
            setPdfMessage(null)
            try {
              const res = await api.post<PdfGenerateResponse>(`/results/${id}/pdf`, {
                languages: ['ru', 'kk', 'en'],
              })
              const langs = res.data.generated.join(', ').toUpperCase() || '—'
              setPdfMessage(`PDF сгенерированы для языков: ${langs}`)
              await load()
            } catch (err: any) {
              setPdfMessage(err?.response?.data?.detail ?? 'Ошибка при генерации PDF')
            } finally {
              setPdfLoading(false)
            }
          }}
        >
          {pdfLoading ? 'Генерация PDF...' : 'Сгенерировать / обновить PDF-отчёты'}
        </button>
        {pdfMessage && <p>{pdfMessage}</p>}
        <div className="pdf-links">
          {data.pdf_ru_path && (
            <a
              className="pdf-link"
              href={`/api/v1/results/${data.id}/pdf/ru`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Скачать RU PDF
            </a>
          )}
          {data.pdf_kk_path && (
            <a
              className="pdf-link"
              href={`/api/v1/results/${data.id}/pdf/kk`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Скачать KK PDF
            </a>
          )}
          {data.pdf_en_path && (
            <a
              className="pdf-link"
              href={`/api/v1/results/${data.id}/pdf/en`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Скачать EN PDF
            </a>
          )}
          {!data.pdf_ru_path && !data.pdf_kk_path && !data.pdf_en_path && !pdfLoading && (
            <p>PDF ещё не сгенерированы — нажмите кнопку выше.</p>
          )}
        </div>
      </section>
    </div>
  )
}

