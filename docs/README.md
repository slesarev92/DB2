# Документация DB2

Индекс актуальных документов проекта. Entry point для нового
разработчика / LLM-агента — читайте файлы в этом порядке:

1. Корневой [`CLAUDE.md`](../CLAUDE.md) — роль, стек, правила работы.
2. [`PATTERNS.md`](PATTERNS.md) — 11 архитектурных паттернов Фазы 1
   (lazy=raise_on_sql, savepoint, soft delete, append-only versioning,
   varchar_enum, etc). Применять везде.
3. [`DEVELOPMENT.md`](DEVELOPMENT.md) — команды dev-стека, frontend
   проверки перед коммитом, prod deploy workflow.
4. [`ADR.md`](ADR.md) — архитектурные решения (11 ADR + 4 ADR-CE для
   расчётного ядра + ADR-16 для AI).
5. [`ROADMAP.md`](ROADMAP.md) — открытые задачи и backlog. История
   фаз с критериями готовности — в `archive/IMPLEMENTATION_PLAN_v1.md`.

## Справочники (обновляются по мере работы)

| Файл | Назначение |
|------|------------|
| [`ERRORS_AND_ISSUES.md`](ERRORS_AND_ISSUES.md) | Журнал проблем + решения. E-01..E-12 — финальные ошибки (asyncpg pools, SAWarning, etc). Добавлять запись при каждом неочевидном баге. |
| [`TZ_VS_EXCEL_DISCREPANCIES.md`](TZ_VS_EXCEL_DISCREPANCIES.md) | Расхождения ТЗ ↔ Excel-эталон. D-01..D-24. **Источник истины формул pipeline.** Excel побеждает ТЗ при конфликте. |
| [`CLIENT_FEEDBACK_v1.md`](CLIENT_FEEDBACK_v1.md) | 40 замечаний заказчика v1 (BUG-01..BUG-12, UX-01..UX-20, LOGIC-01..07) с статусами. |
| [`CLIENT_FEEDBACK_v2.md`](CLIENT_FEEDBACK_v2.md) | **Текущий раунд замечаний заказчика (MEMO от 23.04.2026).** 14 пунктов с приоритетами, 4 блокера в Блоке 1.3. |

## Аудиты (snapshot 2026-04-14/15)

| Файл | Scope |
|------|-------|
| [`ENGINE_AUDIT_REPORT.md`](ENGINE_AUDIT_REPORT.md) | Расчётное ядро: 12-шаговый pipeline, acceptance tests (GORJI drift 0.03%), quick wins roadmap. |
| [`PRESALES_AUDIT_2026-04-14.md`](PRESALES_AUDIT_2026-04-14.md) | Готовность к enterprise-продажам: 5 фаз (математика, invalidation, labels, usability, HelpButton). |
| [`SECURITY_AUDIT_2026-04-14.md`](SECURITY_AUDIT_2026-04-14.md) | OWASP: IDOR (S-01, fixed), prod creds (S-02, rotated), CORS (S-03, verified), rate limiting (S-04, applied v2.4.0). |

Все критичные пункты закрыты в tag `v2.4.0` (2026-04-15). См.
[`CHANGELOG.md`](../CHANGELOG.md) для hi-level summary.

## Операционные инструкции

| Файл | Что описывает |
|------|---------------|
| [`SSL_SETUP.md`](SSL_SETUP.md) | Let's Encrypt через certbot на prod-сервере (85.239.63.206). Host-level SSL → docker nginx :8080. |

## Справочные материалы

- [`ai_samples/`](ai_samples/) — образцы промтов и ответов Polza AI
  (explain_kpi на GORJI и т.п.). Используются как reference для
  тюнинга AI-интеграции.
- [`client_inputs/`](client_inputs/) — исходные материалы от
  заказчика (feedback слайды).
- [`archive/`](archive/) — устаревшие документы (replaced by newer
  or closed trackers). Оставлены для истории.

## Входные документы (root проекта)

ТЗ и эталонные модели лежат в корне репозитория:

- `TZ_Digital_Passport_V3.docx` — основное ТЗ
- `TZ_Addendum.pdf` — дополнения к ТЗ
- `Predikt-k-TZ-V3.xlsx` — Data Dictionary с расчётным pipeline
- `PASSPORT_MODEL_GORJI_2025-09-05.xlsx` — **источник истины формул**
- `PASSPORT_ELEKTRA_ZERO_2025-08-09.pdf` — эталонный паспорт
- `Passport_Examples.pptx` — образцы презентаций

## Версионирование

Git tags — semver (`v2.4.0` — текущая prod-версия, 2026-04-15).

- Последние релизы — в [`CHANGELOG.md`](../CHANGELOG.md) (Unreleased +
  v2.4.0 + v0.3.0)
- Старые релизы — в [`releases/`](releases/) (v0.2.0, v0.1.0 MVP).
  Перенесены 2026-05-12 при чистке документации.
