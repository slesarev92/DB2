# AI Sample — explain-kpi на GORJI reference

**Endpoint:** `POST /api/projects/{id}/ai/explain-kpi`
**Feature:** `AIFeature.EXPLAIN_KPI`
**Default tier:** `BALANCED` → `anthropic/claude-sonnet-4.6`
**Фаза:** 7.2

## Назначение документа

Этот файл — **регрессионный якорь промптов**. При правке
`KPI_EXPLAIN_SYSTEM`/`BASE_TONE_PROMPT` в `backend/app/services/ai_prompts.py`
нужно прогнать endpoint на том же reference-проекте и сравнить новый
ответ с зафиксированным здесь. Резкое отклонение tone/структуры/
рекомендации = промпт сломан, надо катить назад или дорабатывать.

## Как заполнять этот файл

1. Поднять dev-стек, залить GORJI reference (см. `backend/tests/fixtures/gorji_reference.xlsx`)
2. POST `/api/projects/{id}/ai/explain-kpi`:
   ```bash
   curl -X POST http://localhost:8000/api/projects/1/ai/explain-kpi \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"scenario_id": 1, "scope": "y1y5"}'
   ```
3. Скопировать **полный ответ** в секцию "Пример ответа" ниже
4. Отметить в секции "Ручная оценка" насколько ответ осмыслен:
   - Все ли числа из payload упомянуты
   - Соответствует ли tone (без маркетинга, формальный)
   - Корректна ли рекомендация для данных числе NPV/IRR/payback
5. Commit с сообщением `docs(ai): регрессионный якорь explain-kpi GORJI`

## Входные данные (GORJI reference)

TBD — заполнится при ручной проверке. Укажите:

- project_id, scenario_id, scope
- Ключевые KPI фокусного scenario+scope (NPV, IRR, payback, margin)
- WACC проекта, gate_stage

## Пример ответа (заполняется вручную)

```json
{
  "summary": "TBD",
  "key_drivers": [],
  "risks": [],
  "recommendation": "TBD",
  "confidence": 0.0,
  "rationale": "TBD",
  "cost_rub": "0.0",
  "model": "anthropic/claude-sonnet-4.6",
  "cached": false
}
```

**Факт стоимость:** ~? ₽
**Latency:** ~? мс
**Token usage:** prompt ~?k / completion ~?

## Ручная оценка

| Критерий | Оценка | Заметки |
|---|---|---|
| Все числа из payload упомянуты | ☐ | |
| Tone без маркетинга | ☐ | |
| Рекомендация go/no-go/review оправдана | ☐ | |
| Confidence адекватен | ☐ | |
| Key drivers ranked правильно | ☐ | |
| Risks содержательны (не generic) | ☐ | |

## Известные регрессии промптов

Пусто — заполняется если правка промпта внезапно поломала что-то.

## Changelog этого sample

- **2026-04-09** — создан shell с заглушкой TBD (Phase 7.2 commit 2).
  Ручная проверка на GORJI будет выполнена после стабилизации endpoint'а.
