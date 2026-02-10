export interface Task {
  id: number
  created_at: string
  status: string
  file_name?: string | null
  detected_language?: string | null
  risk_level?: string | null
  result_id?: number | null
  error_message?: string | null
  total_tokens?: number | null
}

export interface ResultSummary {
  id: number
  created_at: string
  detected_language: string
  risk_level: string
  total_tokens: number
  file_name?: string | null
}

export interface ResultDetail extends ResultSummary {
  assessment: Record<string, any>
  pdf_ru_path?: string | null
  pdf_kk_path?: string | null
  pdf_en_path?: string | null
}

export interface Stats {
  total_checks: number
  total_tokens: number
  by_language: Record<string, number>
}

export interface Prompts {
  system_message: string
  user_message_template: string
}

export interface PdfGenerateResponse {
  generated: string[]
}

