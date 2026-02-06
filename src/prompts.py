"""Prompts and JSON schema for the test quality assessment agent."""

SYSTEM_MESSAGE = """Ты — эксперт по оценке качества тестовых заданий в медицинском образовании (item review).
Проводи аудит банка тестов в целом: выявляй системные проблемы, риск для валидности, типовые ошибки и давай план улучшений.
Если в тексте нет ключа правильных ответов — НЕ утверждай медицинскую истинность, а помечай риски и требование экспертной верификации.
Никаких общих фраз; вывод должен быть развернутым и практическим.
Возвращай строго JSON, без markdown-блоков, без текста до или после JSON.

ВАЖНО: Все текстовые поля (overall_assessment, title, details, pattern, why_bad, how_to_fix, example_rewrite_template, action, expected_result, reason) должны быть написаны на том же языке, что и исходный текст тестов. Если тесты на русском — пиши на русском, если на казахском — на казахском, если на английском — на английском. НЕ используй английский язык для русских или казахских тестов."""

USER_MESSAGE_TEMPLATE = """Сделай ОБЩЕЕ развернутое заключение по качеству банка тестовых вопросов ниже.
Не делай отчет по каждому вопросу.

Исходный текст тестов на языке: {detected_language}. Учитывай это при оценке language и clarity.

КРИТИЧНО: Верни ВСЕ текстовые поля (overall_assessment, title, details, pattern, why_bad, how_to_fix, example_rewrite_template, action, expected_result, reason) СТРОГО на языке {detected_language}. 

ПРАВИЛА ЯЗЫКА:
- Если detected_language = RU (русский) → ВСЕ текстовые поля на РУССКОМ языке
- Если detected_language = KK (казахский) → ВСЕ текстовые поля на КАЗАХСКОМ языке  
- Если detected_language = EN (английский) → ВСЕ текстовые поля на АНГЛИЙСКОМ языке

НЕ используй английский язык для русских или казахских тестов. НЕ смешивай языки. Каждое текстовое поле должно быть полностью на указанном языке.

Требования:
- Объем overall_assessment: 1200–2500 слов (подробно).
- 6–10 major_findings, с severity и конкретикой.
- 5–8 common_error_patterns с шаблонами исправления.
- action_plan: 7–12 шагов, в логике процесса ЮКМА (автор → эксперт → комиссия → финал).
- spot_check: выбери выборку 15–25 вопросов (по возможности) и укажи только номера "подозрительных" (до 20 шт.) и почему они попали в список (кратко, 1 фраза на номер).
- Если нумерация в тексте неявная — используй порядок следования и присвой номера сам.
- quality_scores: числа от 0 до 10 (единая шкала).
- spot_check.suspicious_question_numbers: максимум 20 элементов.

Верни строго JSON по схеме:
{{
  "overall_assessment": "string",
  "risk_level": "LOW|MEDIUM|HIGH",
  "major_findings": [{{"severity":"HIGH|MEDIUM|LOW","title":"string","details":"string"}}],
  "quality_scores": {{
    "clarity": number,
    "single_best_answer": number,
    "distractors": number,
    "no_clues": number,
    "language": number,
    "structure_consistency": number
  }},
  "common_error_patterns": [
    {{"pattern":"string","why_bad":"string","how_to_fix":"string","example_rewrite_template":"string"}}
  ],
  "action_plan": [{{"step": number, "action":"string","owner":"Автор|Эксперт|Комиссия","expected_result":"string"}}],
  "spot_check": {{
    "sample_size": number,
    "suspicious_question_numbers": [{{"number": number, "reason":"string"}}]
  }}
}}

Текст тестов:
{file_text}"""

# JSON schema for OpenAI Structured Outputs
JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "test_quality_assessment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "overall_assessment": {"type": "string"},
                "risk_level": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH"],
                },
                "major_findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {
                                "type": "string",
                                "enum": ["HIGH", "MEDIUM", "LOW"],
                            },
                            "title": {"type": "string"},
                            "details": {"type": "string"},
                        },
                        "required": ["severity", "title", "details"],
                        "additionalProperties": False,
                    },
                },
                "quality_scores": {
                    "type": "object",
                    "properties": {
                        "clarity": {"type": "number"},
                        "single_best_answer": {"type": "number"},
                        "distractors": {"type": "number"},
                        "no_clues": {"type": "number"},
                        "language": {"type": "number"},
                        "structure_consistency": {"type": "number"},
                    },
                    "required": [
                        "clarity",
                        "single_best_answer",
                        "distractors",
                        "no_clues",
                        "language",
                        "structure_consistency",
                    ],
                    "additionalProperties": False,
                },
                "common_error_patterns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string"},
                            "why_bad": {"type": "string"},
                            "how_to_fix": {"type": "string"},
                            "example_rewrite_template": {"type": "string"},
                        },
                        "required": [
                            "pattern",
                            "why_bad",
                            "how_to_fix",
                            "example_rewrite_template",
                        ],
                        "additionalProperties": False,
                    },
                },
                "action_plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "integer"},
                            "action": {"type": "string"},
                            "owner": {
                                "type": "string",
                                "enum": ["Автор", "Эксперт", "Комиссия"],
                            },
                            "expected_result": {"type": "string"},
                        },
                        "required": [
                            "step",
                            "action",
                            "owner",
                            "expected_result",
                        ],
                        "additionalProperties": False,
                    },
                },
                "spot_check": {
                    "type": "object",
                    "properties": {
                        "sample_size": {"type": "integer"},
                        "suspicious_question_numbers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "number": {"type": "integer"},
                                    "reason": {"type": "string"},
                                },
                                "required": ["number", "reason"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "sample_size",
                        "suspicious_question_numbers",
                    ],
                    "additionalProperties": False,
                },
            },
            "required": [
                "overall_assessment",
                "risk_level",
                "major_findings",
                "quality_scores",
                "common_error_patterns",
                "action_plan",
                "spot_check",
            ],
            "additionalProperties": False,
        },
    },
}
