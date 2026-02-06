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

## Использование

### Веб-интерфейс

```bash
python -m streamlit run app.py
```

Откройте браузер по адресу http://localhost:8501 и загрузите файл .docx. После анализа можно скачать PDF на трёх языках.

### CLI

```bash
python main.py path/to/tests.docx [--output-dir ./output]
```

Результаты сохраняются в:
- `output/ru_pdf/заключение.pdf`
- `output/kk_pdf/заключение.pdf`
- `output/en_pdf/заключение.pdf`

## Формат входа

- Word-документ `.docx` с тестовыми вопросами
- Документ может быть на казахском, русском или английском языке

## Ресурсы

- `assets/header_kolontitul.png` — колонтитул для PDF
- `assets/stamp_test.png` — печать для PDF
