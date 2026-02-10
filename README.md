# AiCheck

ИИ-агент для проверки качества тестовых заданий (банк тестов) в медицинском образовании. Использует OpenAI API для анализа и формирует официальные PDF-заключения на трёх языках: русский, казахский, английский.

## Требования

- Python 3.10+
- OpenAI API key

## Установка

```bash
cd AiCheck
pip install -r requirements.txt
cp .env.example .env
# Отредактируйте .env и укажите OPENAI_API_KEY
```

## Порт (Ubuntu server)

По умолчанию сервис слушает порт **41791** — он выбран так, чтобы не пересекаться с типичными сервисами (22, 80, 443, 3000, 5000, 8000, 8080, 8501 и т.д.). Порт задаётся переменной `PORT` в `.env` (или `AICHECK_PORT`).

## Использование

### Веб-интерфейс

```bash
python -m streamlit run app.py --server.port ${PORT:-41791} --server.address 0.0.0.0
# или на Ubuntu:
chmod +x scripts/run_streamlit.sh && ./scripts/run_streamlit.sh
```

Откройте браузер по адресу http://localhost:41791 (или ваш `PORT`) и загрузите файл .docx.

### CLI

```bash
python main.py path/to/tests.docx [--output-dir ./output]
```

Результаты сохраняются в:
- `output/ru_pdf/заключение.pdf`
- `output/kk_pdf/заключение.pdf`
- `output/en_pdf/заключение.pdf`

### REST API (интеграция с Laravel и др.)

Запуск API-сервера (порт из `PORT` в .env, по умолчанию 41791):

```bash
python api.py
# или
python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-41791}
# на Ubuntu:
chmod +x scripts/run_api.sh && ./scripts/run_api.sh
```

- Документация: http://localhost:41791/docs  
- Проверка: `GET http://localhost:41791/health`  
- Анализ: `POST http://localhost:41791/analyze` или `POST http://localhost:41791/api/v1/analyze` — тело запроса: `multipart/form-data`, поле `file` — файл .docx.

Пример запроса (curl):

```bash
curl -X POST http://localhost:41791/analyze \
  -F "file=@path/to/tests.docx"
```

С опциональным API-ключом (если в .env задан `AICHECK_API_KEY`):

```bash
curl -X POST http://localhost:41791/analyze \
  -H "X-API-Key: your-secret-key" \
  -F "file=@path/to/tests.docx"
```

Ответ 200 — JSON: `risk_level`, `detected_language`, `assessment`, `pdfs` (объект с ключами `ru`, `kk`, `en` — base64-строка PDF). Анализ может занимать 1–5+ минут; на стороне Laravel задайте достаточный timeout (например, 300 секунд).

Пример вызова из Laravel 12:

```php
use Illuminate\Support\Facades\Http;

$response = Http::timeout(300)
    ->attach('file', file_get_contents($pathToDocx), 'tests.docx')
    ->post(config('services.aicheck.url', 'http://localhost:41791') . '/analyze');

if ($response->successful()) {
    $data = $response->json();
    $riskLevel = $data['risk_level'];
    $assessment = $data['assessment'];
    foreach (['ru', 'kk', 'en'] as $lang) {
        $pdfBytes = base64_decode($data['pdfs'][$lang]);
        Storage::put("reports/заключение_{$lang}.pdf", $pdfBytes);
    }
}
```

В `config/services.php` можно добавить: `'aicheck' => ['url' => env('AICHECK_API_URL', 'http://localhost:41791')]`.

## CI/CD

В репозитории настроен GitHub Actions (`.github/workflows/ci.yml`):

- **Триггер:** push и pull request в ветку `release`
- **Шаги:** установка Python 3.11, установка зависимостей, линт (Ruff), тесты (pytest)
- Запуск: при пуше в `main`/`dev` или при создании PR в эти ветки

Локально перед пушем можно выполнить:

```bash
pip install pytest ruff
ruff check .
pytest tests/ -v
```

## Формат входа

- Word-документ `.docx` с тестовыми вопросами
- Документ может быть на казахском, русском или английском языке

## Ресурсы

- `assets/header_kolontitul.png` — колонтитул для PDF
- `assets/stamp_test.png` — печать для PDF
