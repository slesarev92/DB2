"""System/user промпты для AI-фич (Polza AI, Phase 7, ADR-16).

Принципы (ADR-16 «Последствия» + IMPLEMENTATION_PLAN Phase 7):

- **Промпты — Python-константы.** Никаких "промптов из БД" в MVP —
  это создаёт surface для prompt injection. Любое изменение промпта
  проходит через PR review как обычный код.
- **Версионирование через git.** История `git log` этого файла =
  история эволюции промптов.
- **Output — строгий JSON.** Каждый system prompt обязан явно
  инструктировать LLM возвращать JSON по заданной схеме. Pydantic
  на стороне `ai_service.complete_json` валидирует результат и
  поднимает `AIServiceUnavailableError` при несоответствии.
- **Вариативность модели — через параметр `model=`, не через промпт.**
  Для критичных задач вызывающий код передаёт
  `ai_service.COMPLEX_CHAT_MODEL` (claude-opus-4-6), для обычных —
  дефолт claude-sonnet-4-6.

В Phase 7.1 файл пустой — это заглушка под фундамент. Константы
появятся по мере подключения фич:

- Phase 7.2 → `KPI_EXPLAIN_SYSTEM` (объяснение NPV/IRR/Payback)
- Phase 7.3 → `SENSITIVITY_EXPLAIN_SYSTEM` (интерпретация tornado)
- Phase 7.4 → `EXECUTIVE_SUMMARY_SYSTEM` (слайд для PPT)
- Phase 7.6 → `EXECUTIVE_SUMMARY_GENERATION`,
  `PROJECT_GOAL_GENERATION`, `TARGET_AUDIENCE_GENERATION`, ... (15+
  промптов для генерации content fields паспорта)
- Phase 7.7 → `MARKETING_RESEARCH_SYSTEM` (web search)
- Phase 7.8 → `PACKAGE_MOCKUP_STYLE_PRESETS` (расширения user prompt'а
  для image generation)
"""
