# Changelog

Все заметные изменения проекта фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Базовая структура проекта (`backend/`, `frontend/`, `infra/`, `.github/`) согласно ADR-11
- `docs/ADR.md` — 15 архитектурных решений, включая ADR-CE-01..04 (Excel-модель как источник истины для формул расчётного ядра)
- `docs/IMPLEMENTATION_PLAN.md` — план реализации с явно зафиксированным MVP scope и backlog
- `docs/TZ_VS_EXCEL_DISCREPANCIES.md` — 11 расхождений между ТЗ и Excel-моделью, из них 3 критических (D-01 OCF, D-02 VAT, D-03 TAX)
- `docs/ERRORS_AND_ISSUES.md` — журнал проблем и решений
- `CLAUDE.md` — правила работы, стек, раздел "Источник истины для формул"
- `.gitignore`, `.env.example`, `CHANGELOG.md`
- Git-репозиторий инициализирован, первый коммит `chore: init project structure`

Соответствует задаче 0.1 из `docs/IMPLEMENTATION_PLAN.md`.
