"use client";

import { Settings } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { toast } from "sonner";

import {
  ChannelForm,
  EMPTY_CHANNEL_FORM,
  toPscPayload,
  type ChannelFormState,
} from "@/components/projects/channel-form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CollapsibleSection } from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  CHANNEL_GROUP_LABELS,
  CHANNEL_GROUP_ORDER,
  CHANNEL_SOURCE_TYPE_LABELS,
} from "@/lib/channel-group";
import {
  bulkAddChannelsToPsk,
  createChannel,
  listChannels,
  updateChannel,
  updatePskChannel,
} from "@/lib/channels";
import { pluralizeRu } from "@/lib/format";

import type {
  Channel,
  ChannelCreate,
  ChannelGroup,
  ChannelSourceType,
  ProjectSKUChannelDefaults,
  ProjectSKUChannelRead,
} from "@/types/api";

// ============================================================
// Shared form state for catalog create/edit dialogs
// ============================================================

interface ChannelCatalogFormState {
  code: string;
  name: string;
  channel_group: ChannelGroup;
  source_type: ChannelSourceType | "";
  region: string;
  universe_outlets: string;
}

const EMPTY_CATALOG_FORM: ChannelCatalogFormState = {
  code: "",
  name: "",
  channel_group: "OTHER",
  source_type: "custom",
  region: "",
  universe_outlets: "",
};

// ============================================================
// CreateChannelDialog (C #16-T4)
// ============================================================

interface CreateChannelDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Вызывается с созданным каналом — родитель добавит его в список и автоматически чекнет. */
  onCreated: (channel: Channel) => void;
}

export function CreateChannelDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateChannelDialogProps) {
  const [form, setForm] = useState<ChannelCatalogFormState>(EMPTY_CATALOG_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setForm(EMPTY_CATALOG_FORM);
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!form.code.trim() || !form.name.trim()) {
      setError("Код и название обязательны");
      return;
    }
    setSubmitting(true);
    try {
      const payload: ChannelCreate = {
        code: form.code.trim(),
        name: form.name.trim(),
        channel_group: form.channel_group,
        source_type: form.source_type === "" ? null : form.source_type,
        region: form.region.trim() || null,
        universe_outlets:
          form.universe_outlets === "" ? null : Number(form.universe_outlets),
      };
      const channel = await createChannel(payload);
      toast.success(`Канал «${channel.code}» создан`);
      onCreated(channel);
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось создать: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый канал</DialogTitle>
          <DialogDescription>
            Создание кастомного канала. После сохранения он появится в списке
            Фазы 1 и будет автоматически отмечен.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="cch_code">Код *</Label>
            <Input
              id="cch_code"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              maxLength={50}
              disabled={submitting}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cch_name">Название *</Label>
            <Input
              id="cch_name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              maxLength={255}
              disabled={submitting}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cch_group">Группа *</Label>
            <Select
              value={form.channel_group}
              onValueChange={(v) =>
                setForm({ ...form, channel_group: v as ChannelGroup })
              }
              disabled={submitting}
              items={Object.fromEntries(
                CHANNEL_GROUP_ORDER.map((g) => [g, CHANNEL_GROUP_LABELS[g]]),
              )}
            >
              <SelectTrigger id="cch_group">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CHANNEL_GROUP_ORDER.map((g) => (
                  <SelectItem key={g} value={g}>
                    {CHANNEL_GROUP_LABELS[g]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cch_src">Источник данных</Label>
            <Select
              value={form.source_type === "" ? "__none__" : form.source_type}
              onValueChange={(v) =>
                setForm({
                  ...form,
                  source_type: v === "__none__" ? "" : (v as ChannelSourceType),
                })
              }
              disabled={submitting}
              items={{
                __none__: "—",
                ...Object.fromEntries(
                  Object.entries(CHANNEL_SOURCE_TYPE_LABELS),
                ),
              }}
            >
              <SelectTrigger id="cch_src">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {Object.entries(CHANNEL_SOURCE_TYPE_LABELS).map(([k, v]) => (
                  <SelectItem key={k} value={k}>
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="cch_region">Регион</Label>
              <Input
                id="cch_region"
                value={form.region}
                onChange={(e) => setForm({ ...form, region: e.target.value })}
                maxLength={100}
                disabled={submitting}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="cch_universe">ОКБ (шт.)</Label>
              <Input
                id="cch_universe"
                type="number"
                min="0"
                value={form.universe_outlets}
                onChange={(e) =>
                  setForm({ ...form, universe_outlets: e.target.value })
                }
                disabled={submitting}
              />
            </div>
          </div>

          {error !== null && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Создание..." : "Создать"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// EditChannelCatalogDialog (C #16-T4)
// ============================================================

interface EditChannelCatalogDialogProps {
  channel: Channel | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Вызывается после успешного PATCH — родитель обновляет список каналов. */
  onUpdated: (channel: Channel) => void;
}

export function EditChannelCatalogDialog({
  channel,
  open,
  onOpenChange,
  onUpdated,
}: EditChannelCatalogDialogProps) {
  const [form, setForm] = useState<ChannelCatalogFormState>(EMPTY_CATALOG_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && channel !== null) {
      setForm({
        code: channel.code,
        name: channel.name,
        channel_group: channel.channel_group,
        source_type: channel.source_type ?? "",
        region: channel.region ?? "",
        universe_outlets:
          channel.universe_outlets === null
            ? ""
            : String(channel.universe_outlets),
      });
      setError(null);
      setSubmitting(false);
    }
  }, [open, channel]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (channel === null) return;
    setError(null);
    setSubmitting(true);
    try {
      const updated = await updateChannel(channel.id, {
        name: form.name.trim(),
        channel_group: form.channel_group,
        source_type: form.source_type === "" ? null : form.source_type,
        region: form.region.trim() || null,
        universe_outlets:
          form.universe_outlets === "" ? null : Number(form.universe_outlets),
      });
      toast.success(`Канал «${updated.code}» обновлён`);
      onUpdated(updated);
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось сохранить: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Канал «{channel?.code ?? ""}»</DialogTitle>
          <DialogDescription>
            Редактирование канала в каталоге. Изменения видны во всех проектах.
            Код менять нельзя — это якорь для импорта/экспорта.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          {/* code — immutable, только для отображения */}
          <div className="space-y-1">
            <Label htmlFor="ech_code">Код</Label>
            <Input id="ech_code" value={form.code} disabled />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ech_name">Название *</Label>
            <Input
              id="ech_name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              maxLength={255}
              disabled={submitting}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ech_group">Группа *</Label>
            <Select
              value={form.channel_group}
              onValueChange={(v) =>
                setForm({ ...form, channel_group: v as ChannelGroup })
              }
              disabled={submitting}
              items={Object.fromEntries(
                CHANNEL_GROUP_ORDER.map((g) => [g, CHANNEL_GROUP_LABELS[g]]),
              )}
            >
              <SelectTrigger id="ech_group">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CHANNEL_GROUP_ORDER.map((g) => (
                  <SelectItem key={g} value={g}>
                    {CHANNEL_GROUP_LABELS[g]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ech_src">Источник данных</Label>
            <Select
              value={form.source_type === "" ? "__none__" : form.source_type}
              onValueChange={(v) =>
                setForm({
                  ...form,
                  source_type: v === "__none__" ? "" : (v as ChannelSourceType),
                })
              }
              disabled={submitting}
              items={{
                __none__: "—",
                ...Object.fromEntries(
                  Object.entries(CHANNEL_SOURCE_TYPE_LABELS),
                ),
              }}
            >
              <SelectTrigger id="ech_src">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {Object.entries(CHANNEL_SOURCE_TYPE_LABELS).map(([k, v]) => (
                  <SelectItem key={k} value={k}>
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="ech_region">Регион</Label>
              <Input
                id="ech_region"
                value={form.region}
                onChange={(e) => setForm({ ...form, region: e.target.value })}
                maxLength={100}
                disabled={submitting}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ech_universe">ОКБ (шт.)</Label>
              <Input
                id="ech_universe"
                type="number"
                min="0"
                value={form.universe_outlets}
                onChange={(e) =>
                  setForm({ ...form, universe_outlets: e.target.value })
                }
                disabled={submitting}
              />
            </div>
          </div>

          {error !== null && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// AddChannelsDialog (C #16): двухфазный bulk-flow
// ============================================================

type Phase = "pick" | "defaults";

interface AddChannelsDialogProps {
  pskId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** ID каналов которые уже привязаны — в списке отображаются checked + disabled. */
  excludeChannelIds: number[];
  onAdded: () => void;
  /** C #16-T4: триггерится при изменении каталога каналов (создание/правка). */
  onCatalogChanged?: () => void;
}

/**
 * Adapter: ChannelFormState (все строки) → ProjectSKUChannelDefaults.
 * Decimal-поля остаются строками — Pydantic v2 принимает str/float/Decimal
 * одинаково. Empty seasonality → null.
 */
function toDefaultsPayload(
  state: ChannelFormState,
): ProjectSKUChannelDefaults {
  return {
    launch_year: Number(state.launch_year) || 1,
    launch_month: Number(state.launch_month) || 1,
    nd_target: state.nd_target,
    nd_ramp_months: Number(state.nd_ramp_months) || 12,
    offtake_target: state.offtake_target,
    channel_margin: state.channel_margin,
    promo_discount: state.promo_discount,
    promo_share: state.promo_share,
    shelf_price_reg: state.shelf_price_reg,
    logistics_cost_per_kg: state.logistics_cost_per_kg,
    ca_m_rate: state.ca_m_rate,
    marketing_rate: state.marketing_rate,
    seasonality_profile_id:
      state.seasonality_profile_id === ""
        ? null
        : Number(state.seasonality_profile_id),
  };
}

export function AddChannelsDialog({
  pskId,
  open,
  onOpenChange,
  excludeChannelIds,
  onAdded,
  onCatalogChanged,
}: AddChannelsDialogProps) {
  const [phase, setPhase] = useState<Phase>("pick");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [defaults, setDefaults] = useState<ChannelFormState>(EMPTY_CHANNEL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // C #16-T4: sub-dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editingChannel, setEditingChannel] = useState<Channel | null>(null);
  // C #16: collapse state — Map<group, isOpen>. Хранится локально (без LS),
  // потому что в диалоге persistence не нужен; init из defaults вычисляется
  // в useMemo ниже.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const validateRef = useRef<(() => boolean) | null>(null);

  // Загрузка каналов при открытии (вызывается каждый раз — каталог может
  // обновиться через T4 CreateChannelDialog). cancelled flag — стандартный
  // паттерн в проекте (см. channel-form.tsx, channels-panel.tsx).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    listChannels()
      .then((data) => {
        if (cancelled) return;
        setChannels(data);
        setError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Ошибка загрузки каналов");
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Reset формы при закрытии.
  // setChannels([]) — избегаем stale list на следующем open (важно после T4
  // когда каталог можно менять inline).
  useEffect(() => {
    if (open) return;
    setPhase("pick");
    setSelectedIds(new Set());
    setDefaults(EMPTY_CHANNEL_FORM);
    setError(null);
    setSubmitting(false);
    setOpenGroups({});
    setChannels([]);
  }, [open]);

  const excludeSet = useMemo(
    () => new Set(excludeChannelIds),
    [excludeChannelIds],
  );

  // Группировка каналов: Map<group, Channel[]> + сортировка внутри по code.
  const channelsByGroup = useMemo(() => {
    const grouped = new Map<ChannelGroup, Channel[]>();
    for (const c of channels) {
      const arr = grouped.get(c.channel_group) ?? [];
      arr.push(c);
      grouped.set(c.channel_group, arr);
    }
    for (const arr of grouped.values()) {
      arr.sort((a, b) => a.code.localeCompare(b.code, "ru"));
    }
    return grouped;
  }, [channels]);

  // Default состояние свёрнутости групп. Группа открыта, если у неё есть
  // хотя бы один НЕпривязанный канал — иначе сворачиваем для компактности.
  // Init выполняется при первой загрузке каналов; userToggle переопределит.
  useEffect(() => {
    if (channels.length === 0) return;
    const next: Record<string, boolean> = {};
    for (const group of CHANNEL_GROUP_ORDER) {
      const groupChannels = channelsByGroup.get(group) ?? [];
      if (groupChannels.length === 0) continue;
      const hasAvailable = groupChannels.some((c) => !excludeSet.has(c.id));
      next[group] = hasAvailable;
    }
    setOpenGroups((prev) =>
      // Если user уже что-то открыл/закрыл — не перезаписываем
      Object.keys(prev).length === 0 ? next : prev,
    );
  }, [channels, channelsByGroup, excludeSet]);

  // C #16-T4: reload catalog after create/update in sub-dialogs
  function reloadChannels() {
    listChannels()
      .then(setChannels)
      .catch(() => {});
  }

  function handleCatalogCreated(channel: Channel) {
    reloadChannels();
    // Автоматически чекнуть только что созданный канал
    setSelectedIds((prev) => new Set(prev).add(channel.id));
    onCatalogChanged?.();
  }

  function handleCatalogUpdated(_channel: Channel) {
    reloadChannels();
    onCatalogChanged?.();
  }

  const toggleChannel = useCallback((id: number, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const toggleGroup = useCallback((group: ChannelGroup) => {
    setOpenGroups((prev) => ({ ...prev, [group]: !prev[group] }));
  }, []);

  const handleValidateReady = useCallback((fn: () => boolean) => {
    validateRef.current = fn;
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (validateRef.current && !validateRef.current()) return;
    if (selectedIds.size === 0) {
      setError("Выберите хотя бы один канал");
      return;
    }
    setSubmitting(true);
    try {
      const result = await bulkAddChannelsToPsk(pskId, {
        channel_ids: Array.from(selectedIds),
        defaults: toDefaultsPayload(defaults),
      });
      const n = result.length;
      const verb = pluralizeRu(n, "Привязан", "Привязано", "Привязано");
      const noun = pluralizeRu(n, "канал", "канала", "каналов");
      toast.success(`${verb} ${n} ${noun}`);
      onAdded();
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось привязать: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        {phase === "pick" && (
          <>
            <DialogHeader>
              <DialogTitle>Выбор каналов</DialogTitle>
              <DialogDescription>
                Отметьте каналы для привязки к SKU. Метрики (ND, цена, маржа)
                — на следующем шаге, общие для всех выбранных. Точечную
                настройку каждого канала сделаете позже через ✎.
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-[55vh] overflow-y-auto space-y-2 py-2 pr-1">
              {CHANNEL_GROUP_ORDER.map((group) => {
                const groupChannels = channelsByGroup.get(group) ?? [];
                if (groupChannels.length === 0) return null;
                const linkedCount = groupChannels.filter((c) =>
                  excludeSet.has(c.id),
                ).length;
                const isOpen = openGroups[group] ?? false;
                return (
                  <CollapsibleSection
                    key={group}
                    sectionId={`channel-group-${group}`}
                    title={
                      <span>
                        {CHANNEL_GROUP_LABELS[group]}{" "}
                        <span className="text-xs font-normal text-muted-foreground">
                          ({groupChannels.length - linkedCount} из{" "}
                          {groupChannels.length} доступно)
                        </span>
                      </span>
                    }
                    isOpen={isOpen}
                    onToggle={() => toggleGroup(group)}
                  >
                    <div className="space-y-1 pl-3 pb-2">
                      {groupChannels.map((c) => {
                        const isLinked = excludeSet.has(c.id);
                        const isChecked = selectedIds.has(c.id);
                        return (
                          <div
                            key={c.id}
                            className="flex items-center gap-2 py-1"
                          >
                            <Checkbox
                              id={`ch-${c.id}`}
                              checked={isLinked || isChecked}
                              disabled={isLinked}
                              onCheckedChange={(v) =>
                                toggleChannel(c.id, v)
                              }
                            />
                            <label
                              htmlFor={`ch-${c.id}`}
                              className={
                                isLinked
                                  ? "flex-1 text-sm cursor-not-allowed text-muted-foreground"
                                  : "flex-1 text-sm cursor-pointer"
                              }
                            >
                              <span className="font-medium">{c.code}</span>
                              <span className="text-muted-foreground">
                                {" "}
                                — {c.name}
                              </span>
                              {isLinked && (
                                <span className="ml-2 text-xs text-muted-foreground">
                                  (уже привязан)
                                </span>
                              )}
                            </label>
                            {/* C #16-T4: открыть EditChannelCatalogDialog */}
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              aria-label="Редактировать канал в каталоге"
                              onClick={() => setEditingChannel(c)}
                            >
                              <Settings className="size-3.5" aria-hidden />
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                  </CollapsibleSection>
                );
              })}
            </div>

            {error !== null && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <DialogFooter className="flex-row items-center">
              <span className="text-sm text-muted-foreground mr-auto">
                Выбрано: {selectedIds.size}
              </span>
              {/* C #16-T4: открыть CreateChannelDialog */}
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateDialogOpen(true)}
              >
                + Новый канал
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Отмена
              </Button>
              <Button
                type="button"
                onClick={() => setPhase("defaults")}
                disabled={selectedIds.size === 0}
              >
                Далее →
              </Button>
            </DialogFooter>
          </>
        )}

        {phase === "defaults" && (
          <>
            <DialogHeader>
              <DialogTitle>
                Параметры для {selectedIds.size} выбранных каналов
              </DialogTitle>
              <DialogDescription>
                Эти значения применятся ко всем выбранным каналам. Точечную
                настройку по каждому каналу — позже через ✎ в списке.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="space-y-4">
              <ChannelForm
                state={defaults}
                onChange={setDefaults}
                channelHidden
                disabled={submitting}
                onValidate={handleValidateReady}
              />

              {error !== null && (
                <p className="text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setPhase("pick")}
                  disabled={submitting}
                >
                  ← Назад
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting
                    ? "Привязка..."
                    : `Привязать ${selectedIds.size} ${pluralizeRu(selectedIds.size, "канал", "канала", "каналов")}`}
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>

    {/* C #16-T4: sub-dialogs — рендерим вне основного Dialog чтобы
        избежать вложенных Dialog (конфликты z-index и portal в base-ui). */}
    <CreateChannelDialog
      open={createDialogOpen}
      onOpenChange={setCreateDialogOpen}
      onCreated={handleCatalogCreated}
    />
    <EditChannelCatalogDialog
      channel={editingChannel}
      open={editingChannel !== null}
      onOpenChange={(o) => {
        if (!o) setEditingChannel(null);
      }}
      onUpdated={handleCatalogUpdated}
    />
    </>
  );
}

// ============================================================
// EditChannelDialog (PSC metrics — без изменений в C #16-T3)
// ============================================================

interface EditChannelDialogProps {
  pskChannel: ProjectSKUChannelRead | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

function pscToFormState(psc: ProjectSKUChannelRead): ChannelFormState {
  return {
    channel_id: String(psc.channel_id),
    launch_year: String(psc.launch_year),
    launch_month: String(psc.launch_month),
    nd_target: psc.nd_target,
    nd_ramp_months: String(psc.nd_ramp_months),
    offtake_target: psc.offtake_target,
    channel_margin: psc.channel_margin,
    promo_discount: psc.promo_discount,
    promo_share: psc.promo_share,
    shelf_price_reg: psc.shelf_price_reg,
    logistics_cost_per_kg: psc.logistics_cost_per_kg,
    ca_m_rate: psc.ca_m_rate,
    marketing_rate: psc.marketing_rate,
    seasonality_profile_id:
      psc.seasonality_profile_id === null
        ? ""
        : String(psc.seasonality_profile_id),
  };
}

export function EditChannelDialog({
  pskChannel,
  open,
  onOpenChange,
  onSaved,
}: EditChannelDialogProps) {
  const [form, setForm] = useState<ChannelFormState>(EMPTY_CHANNEL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const validateRef = useRef<(() => boolean) | null>(null);

  // Предзаполнение при открытии
  useEffect(() => {
    if (open && pskChannel !== null) {
      setForm(pscToFormState(pskChannel));
      setError(null);
      setSubmitting(false);
    }
  }, [open, pskChannel]);

  const handleValidateReady = useCallback((fn: () => boolean) => {
    validateRef.current = fn;
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pskChannel === null) return;
    setError(null);
    if (validateRef.current && !validateRef.current()) return;
    setSubmitting(true);
    try {
      const payload = toPscPayload(form);
      // channel_id меняться не может на backend (PATCH ignore)
      // — отправляем без него для чистоты.
      const { channel_id: _, ...patch } = payload;
      void _;
      await updatePskChannel(pskChannel.id, patch);
      toast.success("Канал сохранён");
      onSaved();
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось сохранить канал: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Параметры канала{" "}
            {pskChannel !== null
              ? `${pskChannel.channel.code} — ${pskChannel.channel.name}`
              : ""}
          </DialogTitle>
          <DialogDescription>
            Изменения подхватятся при следующем POST /api/projects/{"{id}"}
            /recalculate.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <ChannelForm
            state={form}
            onChange={setForm}
            channelLocked
            disabled={submitting}
            onValidate={handleValidateReady}
          />

          {error !== null && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
