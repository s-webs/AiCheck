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

## Порты

API и дашборд работают на **разных портах** (в `.env`):

- **AICHECK_API_PORT** — REST API (по умолчанию 41791)
- **AICHECK_DASHBOARD_PORT** — устаревший веб-дашборд Streamlit (по умолчанию 41792)

### Запуск API и нового SPA/PWA дашборда

1. Соберите frontend:

```bash
cd AiCheck/frontend
npm install
npm run build
```

В результате появится каталог `frontend/dist`, который FastAPI раздаёт как SPA на корне (`/`).

2. Запустите API-сервер:

```bash
cd AiCheck
python api.py  # или python -m uvicorn api:app --host 0.0.0.0 --port ${AICHECK_API_PORT:-41791}
```

3. Откройте браузер:

- Дашборд SPA/PWA: http://localhost:41791/ (или ваш `AICHECK_API_PORT`)
- Документация API: http://localhost:41791/docs

### Запуск API и старого Streamlit-дашборда одним скриптом (legacy)

Скрипт читает порты из `.env` и запускает обе части приложения:

```bash
python run_all.py
```

Остановка: **Ctrl+C** в консоли (остановит и API, и дашборд).

**Автозагрузка (Windows):** добавьте в автозагрузку запуск, например:
- Ярлык в папке «Автозагрузка» (`Win+R` → `shell:startup`): целевой объект `python C:\путь\к\AiCheck\run_all.py`, рабочая папка `C:\путь\к\AiCheck`.
- Или задание в Планировщике заданий: при входе в систему запускать `python run_all.py`, начальная папка — каталог проекта.

## Использование

### Веб-дашборд (SPA/PWA)

В `.env` задайте логин и пароль для входа в дашборд: `DASHBOARD_USER` и `DASHBOARD_PASSWORD` (см. `.env.example`).  
Дополнительно можно указать срок жизни JWT-токена:

```env
AICHECK_JWT_SECRET=your-very-secret-key
AICHECK_JWT_EXPIRES_MINUTES=4320  # по умолчанию 3 дня
```

После запуска API и сборки фронтенда (см. выше) дашборд доступен по URL:

- http://localhost:41791/  (или ваш `AICHECK_API_PORT`)

В новом SPA доступны разделы:

- **Новая проверка** — загрузка .docx и постановка задачи в очередь.
- **Проверки** — список задач (очередь, в процессе, завершены, ошибки) с переходом к результату.
- **История** — завершённые проверки (дата, язык, риск, токены) с переходом к результату.
- **Результат** — отображение сохранённого заключения по выбранной проверке и ссылок на PDF.
- **Промпты** — редактирование системного и пользовательского промптов агента.
- **Статистика** — агрегированные метрики по проверкам.

#### Legacy: Streamlit-дашборд

Старый дашборд на Streamlit по-прежнему в репозитории, но рекомендуется использовать новый SPA.  
Для запуска legacy-дэшборда:

```bash
# Windows (PowerShell): порт из .env или явно
$env:AICHECK_DASHBOARD_PORT = 41792
python -m streamlit run app.py --server.port $env:AICHECK_DASHBOARD_PORT --server.address 0.0.0.0

# Linux/macOS (bash):
python -m streamlit run app.py --server.port ${AICHECK_DASHBOARD_PORT:-41792} --server.address 0.0.0.0
# или:
chmod x scripts/run_streamlit.sh && ./scripts/run_streamlit.sh
```

Откройте в браузере http://localhost:41792 (или ваш `AICHECK_DASHBOARD_PORT`).

Результаты и история хранятся в SQLite (по умолчанию `data/aicheck.db`; путь задаётся через `DATABASE_URL` в `.env`).

### CLI

```bash
python main.py path/to/tests.docx [--output-dir ./output]
```

Результаты сохраняются в:
- `output/ru_pdf/заключение.pdf`
- `output/kk_pdf/заключение.pdf`
- `output/en_pdf/заключение.pdf`

### REST API (интеграция с Laravel и др.)

Запуск API-сервера (порт из `AICHECK_API_PORT` в .env, по умолчанию 41791):

```bash
python api.py
# или
python -m uvicorn api:app --host 0.0.0.0 --port ${AICHECK_API_PORT:-41791}
# Linux/macOS:
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
    ->post(config('services.aicheck.url', 'http://localhost:41791') . '/analyze');  // AICHECK_API_PORT

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
