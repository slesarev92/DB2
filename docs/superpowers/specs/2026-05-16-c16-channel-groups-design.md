# C #16 — Каналы: группы + source_type (design)

> **Brainstorm session:** 2026-05-16
> **Источник:** MEMO 1.4 / Блок 4.1 / BL-#16 («Каналы: группы (HM/SM/MM/TT/E-COM) + source_type (Nielsen/ЦРПТ/2GIS/Infoline/custom)»).
> **Scope category:** Data model + UX rebuild (bulk-add). Стратегический эпик — разблокирует #15 (P&L pivot), #17 (АКБ авторасчёт), #18 (Waterfall).
> **Prep:** C #30 ввёл `NielsenBenchmarkItem.source_type` для другой сущности (бенчмарки в JSONB) — здесь добавляем `source_type` как **отдельное** поле на `Channel`. Не путать.

---

## §1. Цель

1. **Группировка каналов** для UI и будущих фильтров: добавить колонку `Channel.channel_group` (enum из 8 значений: HM, SM, MM, TT, E_COM, HORECA, QSR, OTHER).
2. **Источник данных** для каждого канала: `Channel.source_type` (enum из 5: nielsen, tsrpt, gis2, infoline, custom; nullable).
3. **Bulk-add UX**: заменить single-channel-select в `AddChannelDialog` на двухфазный flow «чекбоксы по группам → одна общая форма метрик → atomic POST». Под капотом — новый endpoint `POST /api/project-skus/{psk_id}/channels/bulk`.
4. **Inline catalog editing**: в том же диалоге дать редактировать имя/группу/source_type канала (через ✎ кнопку на каждой строке) и создавать кастомные каналы («+ Новый канал»).
5. **Auto-backfill** существующих 25 GORJI seed-каналов в группы по паттерну `code`. Кастомные каналы (если есть на проде) → OTHER. `source_type` всем → NULL.

### §1.1 User stories

- **US-1.** Как продакт, при «+ Привязать канал» я вижу 25+ каналов сгруппированными (HM/SM/MM/TT отдельно, E-COM один блок из 6, HoReCa из 4, QSR из 4) — не скроллю плоский список.
- **US-2.** Как продакт, я чекаю 5-10 каналов сразу, заполняю один блок метрик, и они привязываются за один шаг — не создаю PSC по одному.
- **US-3.** Как админ, я в этом же диалоге создаю кастомный канал «Х5 Чижик» с группой E_COM и source_type=nielsen — без захода в отдельный справочник.
- **US-4.** Как аналитик (для будущих #15/#17/#18), я знаю что каждый канал имеет `channel_group` — могу пивотить P&L по группе, считать АКБ по группе, разбирать водопад unit-эконмики по группе.

---

## §2. Out of scope

| Что | Почему |
|---|---|
| Reference-страница `/reference/channels` для массового редактирования | YAGNI — inline-edit покрывает текущую потребность. Можно добавить позже если bulk-edit понадобится. |
| Bulk PATCH каналов (массово сменить group для 10 каналов) | Достаточно single PATCH через ✎ кнопку. Если массово — отдельная задача после прода-feedback. |
| Bag верстки имени канала (упомянут в CLIENT_FEEDBACK_v2.md) | Не локализован, отдельная mini-задача (см. backlog «#16-followup-name-layout»). Текущий `channels-panel.tsx` уже использует truncate+Tooltip — возможно уже исправлен в C #19/C #22. |
| AI commentary с группировкой каналов | Контекст уже отдаёт `channel.code/name`. Group/source_type AI-context builder начнёт отдавать после рестарта schema, но новых промптов под группировку — не пишем (это под отдельный эпик). |
| Изменение pipeline-расчёта | `channel_group` — описательное поле, не участвует в формулах. Aggregator/exports не меняются в #16 (это работа #15/#17/#18). |
| Pivot по группе в существующем P&L экспорте | Это #15. Здесь только фундамент. |
| Атомарный `actual_import` по группам | Импорт работает через `channel.code` (`actual_import_service.py:14`) — не задеваем. |
| Локализация enum-значений group для других языков | Проект Русский-only. Display-имена групп — в одном frontend-словаре. |

---

## §3. Текущее состояние

### §3.1 Backend

**Модель `Channel`** (`backend/app/models/entities.py:107-122`):
```python
class Channel(Base, TimestampMixin):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    universe_outlets: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

**Pydantic схемы** (`backend/app/schemas/channel.py`): `ChannelRead`, `ChannelCreate`, `ChannelUpdate`. Поля: `id`, `code`, `name`, `region`, `universe_outlets`, `created_at`.

**CRUD endpoints** (`backend/app/api/channels.py`): GET list/one, POST, PATCH, DELETE — всё рабочее.

**Bulk endpoint:** отсутствует. Сейчас фронт добавляет PSC по одному через `POST /api/project-skus/{psk_id}/channels`.

**Seed** (`backend/scripts/seed_reference_data.py:37-63`): 25 каналов с фиксированными codes. Без поля group.

**Использования `channel.code`:**
- `actual_import_service.py:14, 197, 244` — маппинг при импорте Excel
- `export/excel_exporter.py:259`, `ppt_exporter.py:1128-1224`, templates — отображение
- `services/calculation_service.py:492`, `models/entities.py:478, 520, 560` — пояснительные комментарии «TT/E-COM каналы запускаются раньше HM/SM/MM», не машинная логика
- `schemas/pricing.py:10` — `channel_code: str` в read-моделях

**Использования `channel_group`/`ChannelGroup`:** **отсутствуют в коде**. Чистая добавка.

### §3.2 Frontend

**`channels-panel.tsx`** — список привязанных к SKU каналов с возможностью редактирования метрик. Будет переиспользован как есть, изменится только поведение «+ Привязать канал» (откроет новый диалог).

**`channel-dialogs.tsx`** — `AddChannelDialog` (плоский Select + полная форма метрик) и `EditChannelDialog` (правка метрик единичного PSC). `AddChannelDialog` будет переписан на двухфазный flow. `EditChannelDialog` — без изменений.

**`channel-form.tsx`** — `<ChannelForm>` компонент общий для add/edit. Будет иметь новый prop `channelHidden` для Фазы 2 нового диалога (когда channel_id уже выбран множественно).

**`lib/channels.ts`** — список API-обёрток. Сейчас только `listChannels()` (read-only) — нет `createChannel`/`updateChannel`/`bulkAddChannelsToPsk`. Добавим.

**Reference page для каналов:** отсутствует.

---

## §4. Дизайн

### §4.1 Data model

#### §4.1.1 Колонки на `channels`

```python
# backend/app/models/entities.py

ChannelGroup = Literal["HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER"]
ChannelSourceType = Literal["nielsen", "tsrpt", "gis2", "infoline", "custom"]

class Channel(Base, TimestampMixin):
    # ...existing fields...
    channel_group: Mapped[ChannelGroup] = mapped_column(
        varchar_enum(ChannelGroup, "channel_group_value"),
        nullable=False,
        server_default="OTHER",
    )
    source_type: Mapped[ChannelSourceType | None] = mapped_column(
        varchar_enum(ChannelSourceType, "channel_source_type_value"),
        nullable=True,
    )
```

**Naming решение:** колонка названа `channel_group` (не `group`) чтобы избежать SQL reserved word ловушки. Имя enum `ChannelGroup` — компактное (используется через тип-импорт).

**Naming check constraint:** `channel_group_value` / `channel_source_type_value` — суффикс `_value` чтобы не конфликтовать с possible future таблицей `channel_groups` (если она когда-то появится).

**Pattern reference:** PATTERN-08 (varchar + CHECK), `varchar_enum()` helper уже используется для `PackFormat` (C #19), `PeriodType`, `NielsenBenchmarkSourceType` (C #30).

**Server default `"OTHER"`:** safety net — если кто-то INSERT'ит канал без указания group (тесты с минимальными fixtures, скрипты), он попадёт в OTHER. На уровне Pydantic Create — обязательное поле (см. §4.1.2).

#### §4.1.2 Pydantic схемы

```python
# backend/app/schemas/channel.py

ChannelGroup = Literal["HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER"]
ChannelSourceType = Literal["nielsen", "tsrpt", "gis2", "infoline", "custom"]


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    channel_group: ChannelGroup
    source_type: ChannelSourceType | None = None
    region: str | None = None
    universe_outlets: int | None = None
    created_at: datetime


class ChannelCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    channel_group: ChannelGroup
    source_type: ChannelSourceType | None = None
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)


class ChannelUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    channel_group: ChannelGroup | None = None
    source_type: ChannelSourceType | None = None  # patch-able to NULL via explicit "null"
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)
```

#### §4.1.3 TypeScript types

```typescript
// frontend/types/api.ts (или channel-specific lib)

export type ChannelGroup = "HM" | "SM" | "MM" | "TT" | "E_COM" | "HORECA" | "QSR" | "OTHER";
export type ChannelSourceType = "nielsen" | "tsrpt" | "gis2" | "infoline" | "custom";

export interface Channel {
  id: number;
  code: string;
  name: string;
  channel_group: ChannelGroup;
  source_type: ChannelSourceType | null;
  region: string | null;
  universe_outlets: number | null;
  created_at: string;
}
```

И user-facing display dictionary (только frontend):

```typescript
// frontend/lib/channel-group.ts
export const CHANNEL_GROUP_LABELS: Record<ChannelGroup, string> = {
  HM: "Гипермаркеты",
  SM: "Супермаркеты",
  MM: "Минимаркеты",
  TT: "Традиционная розница",
  E_COM: "E-Commerce",
  HORECA: "HoReCa",
  QSR: "QSR / Фастфуд",
  OTHER: "Прочее",
};
export const CHANNEL_GROUP_ORDER: ChannelGroup[] = [
  "HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER",
];
export const CHANNEL_SOURCE_TYPE_LABELS: Record<ChannelSourceType, string> = {
  nielsen: "Nielsen",
  tsrpt: "ЦРПТ",
  gis2: "2GIS",
  infoline: "Infoline",
  custom: "Кастомный",
};
```

### §4.2 Миграция

**Файл:** `backend/migrations/versions/<rev>_c16_channel_group_source_type.py`
**Down revision:** `b9986ce73ab2` (C #24 scenarios.name — текущий head).

#### §4.2.1 Mapping rules (auto-backfill)

```python
MAPPING_RULES: dict[str, str] = {
    # Exact codes
    "HM": "HM",
    "SM": "SM",
    "MM": "MM",
    "TT": "TT",
    "Vkusno I tochka": "QSR",
    "Burger king": "QSR",
    "Rostics": "QSR",
    "Do-Do_pizza": "QSR",
}
PREFIX_RULES: list[tuple[str, str]] = [
    # Prefix matching (ordered: longest prefix first)
    ("E-COM_", "E_COM"),
    ("E_COM_", "E_COM"),
    ("HORECA_", "HORECA"),
]
# Все остальные codes → "OTHER"
```

Применяемая канонизация для 25 GORJI seed-каналов:
- HM, SM, MM, TT → HM/SM/MM/TT (4)
- E-COM_OZ, E-COM_WB, E-COM_YA, E-COM_SBER, E_COM_E-grocery, E-COM_OZ_Fresh → E_COM (6)
- HORECA_АЗС, HORECA_СПОРТ, HORECA_HOTEL, HORECA_Cafe&Rest → HORECA (4)
- Vkusno I tochka, Burger king, Rostics, Do-Do_pizza → QSR (4)
- Beauty, Beauty-NS, DS_Pyaterochka, DS_Magnit, HDS, ALCO, VEND_machine → OTHER (7)

**Итого 25 ↔ 8 групп.** Кастомные коды на проде (если есть) → OTHER.

#### §4.2.2 Алгоритм миграции

```python
def upgrade() -> None:
    # 1. Add columns nullable (чтобы существующие rows не сломались)
    op.add_column("channels", sa.Column("channel_group", sa.String(20), nullable=True))
    op.add_column("channels", sa.Column("source_type", sa.String(20), nullable=True))

    # 2. Backfill channel_group по MAPPING_RULES
    conn = op.get_bind()
    channels = conn.execute(sa.text("SELECT id, code FROM channels")).fetchall()
    for ch_id, code in channels:
        group = _resolve_group(code)  # см. MAPPING_RULES + PREFIX_RULES
        conn.execute(
            sa.text("UPDATE channels SET channel_group = :g WHERE id = :id"),
            {"g": group, "id": ch_id},
        )
    # source_type остаётся NULL для всех — юзер проставит вручную через UI

    # 3. SET NOT NULL + server_default + check constraints
    op.alter_column("channels", "channel_group", nullable=False, server_default="OTHER")
    op.create_check_constraint(
        "valid_channel_group_value",
        "channels",
        "channel_group IN ('HM','SM','MM','TT','E_COM','HORECA','QSR','OTHER')",
    )
    op.create_check_constraint(
        "valid_channel_source_type_value",
        "channels",
        "source_type IS NULL OR source_type IN ('nielsen','tsrpt','gis2','infoline','custom')",
    )

def downgrade() -> None:
    op.drop_constraint("valid_channel_source_type_value", "channels", type_="check")
    op.drop_constraint("valid_channel_group_value", "channels", type_="check")
    op.drop_column("channels", "source_type")
    op.drop_column("channels", "channel_group")
```

**Naming gotcha:** `op.drop_constraint("valid_channel_group_value", ...)` — короткое logical name (см. memory `feedback_phase1_patterns` про двойной префикс). MetaData expansion в alembic превратит в полное `ck_channels_valid_channel_group_value`.

#### §4.2.3 Pre-flight для прода

```sql
-- На сервере перед alembic upgrade head:
SELECT DISTINCT code FROM channels;
-- Сверить с MAPPING_RULES + 25 GORJI codes. Кастомные → OTHER (бесшумно).
-- Если есть кастомные коды, которые юзер хочет в специфическую группу — сделать INSERT/UPDATE до миграции.
```

Включить в `GO5.md` § «Pre-flight для прода» и в CHANGELOG-запись.

### §4.3 Seed update

В `backend/scripts/seed_reference_data.py:37` к каждой строке `CHANNELS_DATA` добавить `"channel_group": "..."`:

```python
CHANNELS_DATA: list[dict[str, Any]] = [
    {"code": "HM", "name": "Гипермаркеты", "channel_group": "HM", "universe_outlets": 822},
    {"code": "SM", "name": "Супермаркеты", "channel_group": "SM", "universe_outlets": 34_083},
    {"code": "MM", "name": "Минимаркеты", "channel_group": "MM", "universe_outlets": 58_080},
    {"code": "TT", "name": "Традиционная розница", "channel_group": "TT", "universe_outlets": 91_444},
    {"code": "Beauty", "name": "Beauty (магазины красоты)", "channel_group": "OTHER", "universe_outlets": 600_000},
    # ... и так далее для всех 25 (источник истины = MAPPING_RULES из миграции)
]
```

`source_type` в seed не задаём (остаётся NULL). На свежем dev-стенде после `python -m scripts.seed_reference_data` миграция дублирует backfill — но это идемпотентно (UPDATE с тем же значением).

### §4.4 API — bulk endpoint

#### §4.4.1 Route

```python
# backend/app/api/project_sku_channels.py

@router.post(
    "/project-skus/{psk_id}/channels/bulk",
    response_model=list[ProjectSKUChannelRead],
    status_code=status.HTTP_201_CREATED,
)
async def bulk_link_channels(
    psk_id: int,
    data: BulkChannelLinkCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectSKUChannelRead]:
    # 1. Загрузить PSK, проверить ownership (existing helper)
    # 2. Вызвать service.bulk_create_psk_channels(session, psk, channel_ids, defaults)
    # 3. await session.commit()
    # 4. Return list[ProjectSKUChannelRead]
```

#### §4.4.2 Pydantic schemas

```python
# backend/app/schemas/project_sku_channel.py

class ProjectSKUChannelDefaults(BaseModel):
    """Метрики применяемые ко всем bulk-каналам. = ProjectSKUChannelCreate минус channel_id."""
    launch_year: int = Field(default=1, ge=1, le=10)
    launch_month: int = Field(default=1, ge=1, le=12)
    nd_target: Decimal = Field(..., ge=0, le=1)
    nd_ramp_months: int = Field(default=12, ge=1, le=36)
    offtake_target: Decimal = Field(..., ge=0)
    channel_margin: Decimal = Field(..., ge=0, le=1)
    promo_discount: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    promo_share: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    shelf_price_reg: Decimal = Field(..., ge=0)
    logistics_cost_per_kg: Decimal = Field(default=Decimal("0"), ge=0)
    ca_m_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    marketing_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    seasonality_profile_id: int | None = None


class BulkChannelLinkCreate(BaseModel):
    channel_ids: list[int] = Field(..., min_length=1, max_length=50)
    defaults: ProjectSKUChannelDefaults
```

#### §4.4.3 Service-логика — reuse существующий `create_psk_channel`

Не дублируем savepoint/predict-генерацию — looped reuse:

```python
# backend/app/services/project_sku_channel_service.py

async def bulk_create_psk_channels(
    session: AsyncSession,
    project_sku_id: int,
    channel_ids: list[int],
    defaults: ProjectSKUChannelDefaults,
) -> list[ProjectSKUChannel]:
    """Создаёт N PSC в одной outer-транзакции. Atomic: всё или ничего.

    Внутри loop'а вызывает существующий `create_psk_channel` для каждого id
    с `auto_fill_predict=True`. Существующий savepoint-pattern (`session.begin_nested()`)
    локализует IntegrityError per-channel; общая транзакция остаётся в endpoint'е.

    Поднимает существующие исключения:
      - `ChannelNotFoundError` (первый невалидный channel_id) → endpoint мапит в 404
      - `ProjectSKUChannelDuplicateError` (первый duplicate) → endpoint мапит в 409
    """
    created: list[ProjectSKUChannel] = []
    for ch_id in channel_ids:
        data = ProjectSKUChannelCreate(channel_id=ch_id, **defaults.model_dump())
        psc = await create_psk_channel(session, project_sku_id, data)
        created.append(psc)
    return created
```

**Atomic guarantee:** endpoint не commit'ит до завершения loop'а. На любой raise — FastAPI откатит outer transaction. Все ранее flushed PSC откатятся вместе.

**Сообщения об ошибках:** endpoint мапит первое исключение в HTTP-код. Фронту видно: «канал X уже привязан» (только первый дубль). Юзер исправит и нажмёт снова. Альтернатива (валидировать all-up-front, отдать список missing/duplicate ids) — переусложнение для MVP, добавим если жалобы поступят.

#### §4.4.4 Endpoint реализация

```python
# backend/app/api/project_sku_channels.py

@router.post(
    "/api/project-skus/{psk_id}/channels/bulk",
    response_model=list[ProjectSKUChannelRead],
    status_code=status.HTTP_201_CREATED,
)
async def bulk_link_channels_endpoint(
    psk_id: int,
    data: BulkChannelLinkCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectSKUChannelRead]:
    psk = await _require_psk_owned(session, psk_id, current_user)

    try:
        created = await project_sku_channel_service.bulk_create_psk_channels(
            session, psk_id, data.channel_ids, data.defaults
        )
    except project_sku_channel_service.ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more channel_ids not found",
        )
    except project_sku_channel_service.ProjectSKUChannelDuplicateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more channels already attached to this ProjectSKU",
        )

    await invalidation_service.mark_project_stale(session, psk.project_id)
    await session.commit()
    return [ProjectSKUChannelRead.model_validate(psc) for psc in created]
```

#### §4.4.4 Существующий single endpoint — не меняем

`POST /api/project-skus/{psk_id}/channels` (single channel) остаётся для случая «добавил один кастомный канал после первоначального bulk».

### §4.5 Frontend UX

#### §4.5.1 Новый `AddChannelsDialog` (rebuilt)

Файл: `frontend/components/projects/channel-dialogs.tsx` — экспортируем новый компонент `AddChannelsDialog` (множественное число), оставляем старый `AddChannelDialog` deprecated → удалить после миграции вызовов.

**State machine:**
```typescript
type Phase = "pick" | "defaults";
const [phase, setPhase] = useState<Phase>("pick");
const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
const [defaults, setDefaults] = useState<ChannelFormState>(EMPTY_CHANNEL_FORM);
```

**Фаза 1 — Pick:**

```tsx
<DialogContent className="sm:max-w-2xl">
  <DialogHeader>
    <DialogTitle>Выбор каналов для SKU</DialogTitle>
    <DialogDescription>
      Чекните каналы которые хотите привязать. Метрики (ND, цена, маржа) — на следующем шаге, одни для всех выбранных.
    </DialogDescription>
  </DialogHeader>

  <div className="max-h-[60vh] overflow-y-auto space-y-2">
    {CHANNEL_GROUP_ORDER.map((group) => {
      const groupChannels = channelsByGroup[group] ?? [];
      if (groupChannels.length === 0) return null;
      return (
        <CollapsibleSection
          key={group}
          title={`${CHANNEL_GROUP_LABELS[group]} (${groupChannels.length})`}
          defaultOpen={groupChannels.some((c) => !excludeIds.has(c.id))}
        >
          {groupChannels.map((c) => {
            const isLinked = excludeIds.has(c.id);
            const isChecked = selectedIds.has(c.id);
            return (
              <div key={c.id} className="flex items-center gap-2 py-1">
                <Checkbox
                  checked={isLinked || isChecked}
                  disabled={isLinked}
                  onCheckedChange={(v) => toggleChannel(c.id, !!v)}
                />
                <span className="flex-1 text-sm">
                  <span className="font-medium">{c.code}</span>
                  <span className="text-muted-foreground"> — {c.name}</span>
                  {isLinked && <span className="ml-2 text-xs text-muted-foreground">(уже привязан)</span>}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={() => openCatalogEdit(c)}
                >
                  <Settings className="h-3 w-3" />
                </Button>
              </div>
            );
          })}
        </CollapsibleSection>
      );
    })}
  </div>

  <Button variant="outline" size="sm" onClick={openCreate}>
    + Новый канал
  </Button>

  <DialogFooter>
    <span className="text-sm text-muted-foreground mr-auto">
      Выбрано: {selectedIds.size}
    </span>
    <Button variant="outline" onClick={() => onOpenChange(false)}>Отмена</Button>
    <Button onClick={() => setPhase("defaults")} disabled={selectedIds.size === 0}>
      Далее →
    </Button>
  </DialogFooter>
</DialogContent>
```

**Фаза 2 — Defaults:**

```tsx
<DialogHeader>
  <DialogTitle>Параметры для {selectedIds.size} выбранных каналов</DialogTitle>
  <DialogDescription>
    Одни значения применятся ко всем выбранным каналам. Тонкая настройка по каждому — позже через ✎ в списке.
  </DialogDescription>
</DialogHeader>

<form onSubmit={handleSubmit}>
  <ChannelForm
    state={defaults}
    onChange={setDefaults}
    channelHidden  /* НОВЫЙ prop: скрывает channel_id Select */
    onValidate={handleValidateReady}
  />

  <DialogFooter>
    <Button variant="outline" onClick={() => setPhase("pick")}>← Назад</Button>
    <Button type="submit">Привязать {selectedIds.size} каналов</Button>
  </DialogFooter>
</form>
```

**Submit:**
```typescript
async function handleSubmit(e: FormEvent) {
  e.preventDefault();
  if (!validateRef.current?.()) return;
  setSubmitting(true);
  try {
    const result = await bulkAddChannelsToPsk(pskId, {
      channel_ids: Array.from(selectedIds),
      defaults: toPscDefaultsPayload(defaults),  // ChannelFormState → ProjectSKUChannelDefaults
    });
    toast.success(`Привязано ${result.length} каналов`);
    onAdded();
    onOpenChange(false);
  } catch (err) {
    toast.error(`Не удалось привязать: ${formatError(err)}`);
    setSubmitting(false);
  }
}
```

#### §4.5.2 `CreateChannelDialog` (sub-dialog)

Создание кастомного канала прямо из `AddChannelsDialog`:

```tsx
<Dialog>
  <DialogContent className="sm:max-w-md">
    <DialogHeader><DialogTitle>Новый канал</DialogTitle></DialogHeader>
    <form onSubmit={handleSubmit} className="space-y-3">
      <Input label="Код" value={code} required maxLength={50} />
      <Input label="Название" value={name} required maxLength={255} />
      <Select label="Группа" value={group} options={CHANNEL_GROUP_LABELS} required />
      <Select label="Источник данных" value={sourceType} options={CHANNEL_SOURCE_TYPE_LABELS} placeholder="—" />
      <Input label="Регион (опц.)" value={region} maxLength={100} />
      <Input label="ОКБ (опц., шт.)" value={universeOutlets} type="number" min="0" />
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Отмена</Button>
        <Button type="submit">Создать</Button>
      </DialogFooter>
    </form>
  </DialogContent>
</Dialog>
```

Submit → `POST /api/channels` → toast → onCreated callback → родительский `AddChannelsDialog` подгружает обновлённый список каналов и автоматически чекает новосозданный.

#### §4.5.3 `EditChannelCatalogDialog` (sub-dialog)

Открывается из `AddChannelsDialog` по кнопке ⚙ (Settings icon) рядом с каналом:

```tsx
<Dialog>
  <DialogContent className="sm:max-w-md">
    <DialogHeader><DialogTitle>Редактирование канала «{channel.code}»</DialogTitle></DialogHeader>
    <form onSubmit={handleSubmit} className="space-y-3">
      {/* code disabled — immutable */}
      <Input label="Код" value={channel.code} disabled />
      <Input label="Название" value={name} required />
      <Select label="Группа" value={group} options={...} required />
      <Select label="Источник данных" value={sourceType} options={...} />
      <Input label="Регион" value={region} />
      <Input label="ОКБ" value={universeOutlets} type="number" />
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Отмена</Button>
        <Button type="submit">Сохранить</Button>
      </DialogFooter>
    </form>
  </DialogContent>
</Dialog>
```

Submit → `PATCH /api/channels/{id}` → reload list.

**Визуальное разделение catalog ✎ vs PSC ✎:**
- В `AddChannelsDialog` (catalog edit) — иконка `<Settings>` (шестерёнка)
- В `ChannelsPanel` (PSC metrics edit) — иконка `<Pencil>` (текущее `✎`)
Юзер видит две разные иконки → не путает «редактировать канал в справочнике» с «редактировать метрики этого SKU на канале».

#### §4.5.4 `frontend/lib/channels.ts` — additions

```typescript
export function createChannel(data: ChannelCreate): Promise<Channel> {
  return apiPost<Channel>("/api/channels", data);
}

export function updateChannel(id: number, data: ChannelUpdate): Promise<Channel> {
  return apiPatch<Channel>(`/api/channels/${id}`, data);
}

export function bulkAddChannelsToPsk(
  pskId: number,
  data: BulkChannelLinkCreate,
): Promise<ProjectSKUChannelRead[]> {
  return apiPost<ProjectSKUChannelRead[]>(
    `/api/project-skus/${pskId}/channels/bulk`,
    data,
  );
}
```

И типы (`frontend/types/api.ts`): добавить `BulkChannelLinkCreate`, `ProjectSKUChannelDefaults`, `ChannelGroup`, `ChannelSourceType`, обновить `Channel` и `ChannelCreate`/`ChannelUpdate`.

#### §4.5.5 Что не меняем во фронте

- `channels-panel.tsx` — оставляем как есть, **только** меняем `<AddChannelDialog>` → `<AddChannelsDialog>` (множ. число) и обновляем prop signature.
- `EditChannelDialog` (правка PSC metrics) — без изменений.
- `ChannelForm` — единственное изменение: новый prop `channelHidden?: boolean` (скрывает Select `channel_id` блок). Backward-compat.

### §4.6 Тестирование

#### §4.6.1 Backend tests

**`tests/migrations/test_c16_backfill.py`** (новый):
- `test_resolve_group_exact_match` — HM→HM, TT→TT, Vkusno I tochka→QSR
- `test_resolve_group_prefix` — E-COM_OZ→E_COM, HORECA_АЗС→HORECA
- `test_resolve_group_fallback_other` — Beauty→OTHER, неизвестный код→OTHER

**`tests/services/test_channel_service.py`** (расширить):
- `test_create_channel_with_group_and_source` — POST с `channel_group="HM"`, `source_type="nielsen"` → проверить запись
- `test_patch_channel_group` — PATCH `channel_group` от OTHER к HM
- `test_create_channel_invalid_group` — Pydantic 422 на `channel_group="WTF"`
- `test_create_channel_invalid_source_type` — Pydantic 422 на `source_type="other"`

**`tests/services/test_project_sku_channel_service.py`** (расширить или новый):
- `test_bulk_create_pscs_success` — создаёт 3 PSC за раз, возвращает 3 ProjectSKUChannelRead, predict-layer создан
- `test_bulk_create_duplicate_returns_409` — попытка bulk с уже привязанным каналом → 409, ноль изменений
- `test_bulk_create_missing_channel_returns_404` — `channel_ids=[999]` → 404
- `test_bulk_create_atomic_rollback` — на симулированной ошибке в predict-layer все созданные PSC откатываются
- `test_bulk_create_predict_layer_generated` — после bulk у каждого нового PSC есть 43×3 PeriodValue

**`tests/api/test_channels.py`** (расширить):
- `test_list_channels_includes_group_field` — GET /api/channels → каждый ChannelRead имеет `channel_group`

#### §4.6.2 Frontend smoke

После реализации (ручной smoke):
1. `npx tsc --noEmit` — 0 ошибок.
2. Открыть `/projects/{gorji_id}/channels` → выбрать SKU → «+ Привязать канал».
3. Развернуть группу HoReCa → чекнуть 2 канала → Далее → заполнить ND/offtake → Привязать.
4. Проверить что 2 строки появились в `ChannelsPanel`.
5. Открыть диалог снова → нажать «+ Новый канал» → создать «X5 Чижик» (E_COM, nielsen) → submit → канал появляется в E_COM группе → автоматически чекнут.
6. Кликнуть ⚙ на любом канале → изменить имя → сохранить → проверить обновление.
7. Acceptance GORJI (`pytest tests/acceptance -m acceptance`) → 6 passed, drift < 0.03%.

### §4.7 CHANGELOG + docs

**`CHANGELOG.md` (Unreleased):**
```markdown
### Added
- C #16: каналы получили поля `channel_group` (HM/SM/MM/TT/E_COM/HORECA/QSR/OTHER) и `source_type` (Nielsen/ЦРПТ/2GIS/Infoline/custom). Существующие 25 GORJI seed-каналов автоматически отмапплены в группы. (MEMO 1.4)
- C #16: новый bulk endpoint `POST /api/project-skus/{psk_id}/channels/bulk` для привязки нескольких каналов к SKU за одну транзакцию.
- C #16: двухфазный диалог «+ Привязать канал» (выбор чекбоксами по группам → одна форма метрик).
- C #16: inline-редактирование каталога каналов из add-диалога (создать новый, изменить имя/группу/source_type существующего).

### Migrations
- `c16_channel_group_source_type` — добавлены `channels.channel_group` (NOT NULL, default OTHER, CHECK 8 значений) и `channels.source_type` (nullable, CHECK 5 значений). Auto-backfill для 25 seed-кодов.

### Pre-flight for prod
Перед `alembic upgrade head` сверить `SELECT DISTINCT code FROM channels` с MAPPING_RULES (в миграции `<rev>_c16_channel_group_source_type.py`). Незнакомые коды попадают в OTHER (тихо). Если есть кастомные каналы которые юзер хочет в другую группу — сделать UPDATE до миграции.
```

**Документация:**
- Обновить `docs/CLIENT_FEEDBACK_v2_STATUS.md`: отметить «Чекбоксы с группировкой HM/SM/MM/TT/E-COM ✅», «Источник данных source_type ✅», «Кастомный канал ✅».
- Обновить `GO5.md` § «Pre-flight для прода» — добавить запись про C #16 (как сейчас есть запись про C #19).
- Не нужен новый ADR (это feature, не архитектурное решение).

---

## §5. Subagent-driven план — skeleton

Эпик #16 = **5 задач**, single branch `feat/c16-channel-groups`:

| # | Задача | Файлы | Модель | Зависит от |
|---|---|---|---|---|
| **T1** | Schema (`Channel.channel_group`+`source_type`) + миграция + auto-backfill + seed update + 4 миграционных теста + 2 channel CRUD-теста | `backend/app/models/entities.py`, `backend/app/schemas/channel.py`, `backend/migrations/versions/*`, `backend/scripts/seed_reference_data.py`, `backend/tests/migrations/*`, `backend/tests/api/test_channels.py` | sonnet | — |
| **T2** | Bulk endpoint + service + Pydantic schemas + 5 bulk-tests | `backend/app/api/project_sku_channels.py`, `backend/app/schemas/project_sku_channel.py`, `backend/app/services/project_sku_channel_service.py`, `backend/tests/services/test_project_sku_channel_service.py` | sonnet | T1 (нужны новые типы для read) |
| **T3** | Frontend: новый `AddChannelsDialog` (двухфазный) + grouping logic + `lib/channel-group.ts` + types | `frontend/components/projects/channel-dialogs.tsx`, `frontend/components/projects/channels-panel.tsx` (мини-правка vendor), `frontend/lib/channel-group.ts`, `frontend/types/api.ts`, `frontend/lib/channels.ts` (bulk + create/update) | **opus** | T2 (нужен bulk endpoint) |
| **T4** | Frontend: `CreateChannelDialog` + `EditChannelCatalogDialog` + hookup в Фазу 1 | `frontend/components/projects/channel-dialogs.tsx` (extend) | sonnet | T3 |
| **T5** | Integration smoke + acceptance GORJI + tsc --noEmit + CHANGELOG + docs updates | manual smoke + `docs/CLIENT_FEEDBACK_v2_STATUS.md`, `CHANGELOG.md`, `GO5.md` | sonnet | T1-T4 |

**Controller (я) — между задачами:**
- После T1 — проверить миграция `alembic upgrade head` & `alembic downgrade -1 && upgrade head` идемпотентность
- После T2 — проверить bulk endpoint с реальной БД (curl)
- После T3 — обязательный restart frontend + purge .next (memory `feedback-frontend-structural-restart`)
- После T5 — full pytest + tsc + GORJI acceptance + commit + merge to main

**Параллелизация:** T2 и T3 не могут идти параллельно (T3 зависит от endpoint). T4 — последовательно за T3. Все 5 — линейные.

---

## §6. Открытые вопросы

Нет. Все решения зафиксированы в §4. Если в ходе реализации появится drift — открыть issue/CHANGELOG note без пересмотра спеки.

---

## §7. Ссылки

- MEMO 1.4 / Блок 4.1 → `docs/CLIENT_FEEDBACK_v2.md:109-119`
- Status матрица → `docs/CLIENT_FEEDBACK_v2_STATUS.md:115-121`
- Memory `feedback-subagent-driven-workflow` — workflow для multi-task эпиков DB2
- Memory `feedback-phase1-patterns` — PATTERN-08 varchar_enum + check constraint
- Memory `feedback-frontend-structural-restart` — restart+purge .next после структурных JSX изменений
- C #19 spec (`2026-05-16-c19-pack-format-enum-design.md`) — паттерн enum-миграции с MAPPING_RULES
- C #30 spec (`NielsenBenchmarkItem.source_type` — другая сущность, не путать)
