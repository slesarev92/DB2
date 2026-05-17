# C #17 — АКБ автоматический расчёт (design)

> **Brainstorm session:** 2026-05-17 (compressed)
> **Источник:** MEMO 1.4 / Block 4.3 / BL-#17.
> **Scope:** Read-only computed endpoint + UI секция. Не трогаем existing AKBEntry CRUD.

---

## §1. Цель

Заменить ручной ввод АКБ на автоматический расчёт: для каждой пары `(SKU, Channel)` вычисляется `target_outlets = nd_target × channel.universe_outlets`.

### §1.1 User story

«Я не хочу вручную вписывать ОКБ для каждого канала — она уже в каталоге. Просто покажи мне сколько целевых ТТ при моём nd_target (численная дистрибуция %). И сгруппируй по группам каналов из #16, чтобы я видел план HM/SM/MM/TT/E_COM».

---

## §2. Out of scope

| Что | Почему |
|---|---|
| Миграция AKBEntry в computed view (drop таблицы) | Pre-existing manual entries не теряем — добавляем computed-секцию **поверх**. |
| Persisted snapshot computed value | Live-computed. Изменение nd_target / universe_outlets → автоматически отражается. |
| Per-period (помесячная) АКБ с рамп-апом | `nd_target` уже имеет `nd_ramp_months` — рамп-ап в pipeline. Здесь — target цифра (steady state). |
| Override (manual > computed) | Если нужен override — юзер всё ещё может создать AKBEntry вручную (existing CRUD). |

---

## §3. Текущее состояние

### Backend
- `app/models/entities.py`: `AKBEntry` (project_id, channel_id, universe_outlets, target_outlets, coverage_pct, weighted_distribution) — manual.
- `app/services/akb_service.py`: CRUD list/get/create/update/delete.
- `app/api/akb.py`: endpoints CRUD.
- `ProjectSKUChannel.nd_target: Decimal` — целевая численная дистрибуция (0..1).
- `Channel.universe_outlets: int | None` — ОКБ.
- `Channel.channel_group` (C #16) — для агрегации.

### Frontend
- `components/projects/akb-tab.tsx` — таблица AKBEntry, форма add, sort.
- `lib/akb.ts` — API обёртки.

---

## §4. Дизайн

### §4.1 Backend — auto endpoint

`GET /api/projects/{project_id}/akb/auto` → `list[AKBAutoEntry]`:

```python
# app/schemas/akb.py — добавить:

class AKBAutoEntry(BaseModel):
    """Computed entry: nd_target × channel.universe_outlets per (PSK × Channel)."""
    psk_id: int
    sku_id: int
    sku_brand: str
    sku_name: str
    channel_id: int
    channel_code: str
    channel_name: str
    channel_group: ChannelGroup
    universe_outlets: int | None  # ОКБ из Channel
    nd_target: Decimal              # численная дистрибуция (0..1)
    target_outlets: int | None      # = round(nd_target * universe_outlets) если оба заданы
```

Service:
```python
async def compute_auto_entries(session, project_id) -> list[AKBAutoEntry]:
    # SELECT psk × channel through ProjectSKUChannel + Channel + SKU joins
    # Filter: psk.project_id == project_id
    # Compute target_outlets = round(nd_target * universe_outlets) если universe_outlets is not None
    # Sort by channel_group order, then channel.code, then sku.brand/name
```

Endpoint в `app/api/akb.py` — добавить новый route `GET /api/projects/{project_id}/akb/auto`.

### §4.2 Backend tests

- `test_akb_auto_empty_project_returns_empty_list`
- `test_akb_auto_returns_psk_channel_combinations`
- `test_akb_auto_target_outlets_computed` — assert `target = round(nd * universe)`
- `test_akb_auto_universe_none_returns_target_none`

### §4.3 Frontend

В `akb-tab.tsx` добавить **новую секцию выше существующей**:

```tsx
<Card>
  <CardHeader>
    <CardTitle>Авто-расчёт АКБ (nd × ОКБ)</CardTitle>
    <CardDescription>
      Целевые ТТ автоматически = % дистрибуции × ОКБ канала.
      Меняйте параметры на вкладке «Каналы» — обновится здесь.
    </CardDescription>
  </CardHeader>
  <CardContent>
    {/* Tab toggle: per-SKU table | aggregate по channel_group */}
    {/* Table: SKU | Channel (group: code) | ОКБ | ND% | Target ТТ */}
    {/* Aggregate: Group | Σ universe | avg ND | Σ target */}
  </CardContent>
</Card>
```

Existing AKBEntry CRUD таблица переносится ниже под title «Ручные записи АКБ (legacy)».

`lib/akb.ts` — добавить:
```typescript
export function listAkbAuto(projectId: number): Promise<AKBAutoEntry[]> {
  return apiGet<AKBAutoEntry[]>(`/api/projects/${projectId}/akb/auto`);
}
```

TS типы из backend Pydantic.

### §4.4 Tests

Backend (4 теста). Frontend: tsc clean.

---

## §5. Plan skeleton (3 задачи)

| # | Задача | Файлы |
|---|---|---|
| T1 | Backend: AKBAutoEntry schema + service compute + endpoint + 4 теста | schemas/akb.py, services/akb_service.py, api/akb.py, tests/api/test_akb.py |
| T2 | Frontend: lib/akb.ts (listAkbAuto) + типы + akb-tab.tsx (auto-секция + aggregate view) | lib/akb.ts, types/api.ts, components/projects/akb-tab.tsx |
| T3 | docs + merge | CHANGELOG, GO5 |

Branch: `feat/c17-akb-auto-calc`. Tag: `v2.6.8`.
