# C #21 — Status проекта + ручная раскраска Gantt (design)

> **Brainstorm session:** 2026-05-16 (compressed)
> **Источник:** MEMO 1.4 / Block 11 / BL-#21. Часть закрыта A.3 (roadmap_tasks.status dropdown). Здесь — оставшееся: project-level status + manual color override на Gantt-задачах.
> **Scope:** Backend (Project.status enum + migration) + frontend (UI selector + Gantt color override).

---

## §1. Цель

Две независимых, но связанных фичи:

1. **Project-level status.** Помимо `gate_stage` (G0..G5 — стадии gate-review), добавляется **lifecycle status** — `draft` / `active` / `paused` / `cancelled` / `completed` / `archived`. Отдельная семантика, отдельный flow.
2. **Manual color override** на задачи Gantt. Сейчас цвет вычисляется из `status` (`done`/`in_progress`/`planned`/`blocked`). Юзер может хочет выделить milestone своим цветом — добавляется optional `color` field на task object внутри `roadmap_tasks` JSONB list.

### §1.1 User stories

- US-1. Я открываю список проектов, вижу бейдж «Активный» / «Архив» / «Черновик» — фильтрую по статусу.
- US-2. У меня есть задача-milestone в Gantt, я хочу выделить её фиолетовым (не из 4 статусов) — кликаю color picker рядом со status, выбираю #a855f7.

---

## §2. Out of scope

| Что | Почему |
|---|---|
| Фильтр списка проектов по lifecycle status | YAGNI на этой итерации — добавим если попросят. |
| Workflow rules (active → completed только через UI button) | Допускаем direct PATCH между всеми статусами. |
| Цвета в RGBA / hex picker library | Native HTML `<input type="color">` достаточно. |
| Per-cell color на gate_stage / G-ячейках | Не Gantt task'и, не этот scope. |
| Notification про статус-изменение | YAGNI. |

---

## §3. Текущее состояние

### Backend
- `backend/app/models/entities.py` Project — есть `gate_stage: GateStage | None`. **Нет** lifecycle status.
- `roadmap_tasks: JSONB list[Any]` — каждый item имеет `name, start_date, end_date, status, owner` (используется в `gantt-chart.tsx`). `color` нет.

### Frontend
- `gantt-chart.tsx` использует `STATUS_COLORS` + `STATUS_LEGACY_MAP` для маппинга. Manual color override отсутствует.
- В project header / list нет status badge.

---

## §4. Дизайн

### §4.1 Project.status — backend

```python
ProjectStatus = Literal["draft", "active", "paused", "cancelled", "completed", "archived"]

class Project(...):
    # ...
    status: Mapped[ProjectStatus] = mapped_column(
        String(20),
        nullable=False,
        server_default="active",
    )
```

Server default `"active"` для существующих — все они «активные» по факту. Юзер может перевести в draft/archived вручную.

Migration: добавление колонки nullable → backfill 'active' → SET NOT NULL + CHECK constraint.

Pydantic:
```python
ProjectStatus = Literal["draft", "active", "paused", "cancelled", "completed", "archived"]

# ProjectBase
status: ProjectStatus = "active"

# ProjectUpdate
status: ProjectStatus | None = None
```

### §4.2 RoadmapTask color override — JSONB-only, без миграции

`roadmap_tasks` уже `list[Any]` JSONB. Добавление optional поля `color?: string` на каждом item — backward-compat. Без миграции и без Pydantic-валидации — frontend знает что `task.color: string | null`.

### §4.3 Frontend types

```typescript
export type ProjectStatus =
  | "draft"
  | "active"
  | "paused"
  | "cancelled"
  | "completed"
  | "archived";

export interface ProjectRead {
  status: ProjectStatus;
}

export interface RoadmapTask {
  color?: string | null;
}
```

### §4.4 UI

**Project header (на странице проекта `/projects/[id]`):**
- Status badge рядом с именем проекта (color-coded)
- Click → dropdown с 6 опциями → PATCH

**Labels + colors:**
```typescript
export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  draft: "Черновик",
  active: "Активный",
  paused: "Приостановлен",
  cancelled: "Отменён",
  completed: "Завершён",
  archived: "Архив",
};
export const PROJECT_STATUS_COLORS: Record<ProjectStatus, string> = {
  draft: "bg-gray-100 text-gray-700",
  active: "bg-blue-100 text-blue-700",
  paused: "bg-amber-100 text-amber-700",
  cancelled: "bg-red-100 text-red-700",
  completed: "bg-green-100 text-green-700",
  archived: "bg-slate-100 text-slate-500",
};
```

**Roadmap task edit (где-то в content-tab.tsx):**
- Native `<input type="color">` рядом с status select
- Empty value (clear) = revert to status-based color
- `task.color` сохраняется в JSONB

**Gantt color resolution:**
```typescript
const fill = entry.color || statusColor(entry.status);
```

### §4.5 Tests

Backend (4):
- `test_project_status_default_active`
- `test_project_status_create_draft`
- `test_project_status_patch`
- `test_project_status_invalid_422`

Frontend: tsc clean.

---

## §5. Plan skeleton (3 задачи)

| # | Задача | Файлы |
|---|---|---|
| T1 | Backend: Project.status + миграция + schemas + 4 теста | model, schema, migration, test_projects |
| T2 | Frontend: ProjectStatus тип + status badge в project header + roadmap task color picker + Gantt fallback | types, lib/project-status.ts, project header component, content-tab.tsx (roadmap edit), gantt-chart.tsx |
| T3 | docs + merge | CHANGELOG, GO5 |

Branch: `feat/c21-project-status-gantt`. Tag после merge: `v2.6.7`.
