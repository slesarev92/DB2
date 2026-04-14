"use client";

import { useEffect, useState } from "react";

import { FieldError } from "@/components/ui/field-error";
import { HelpButton } from "@/components/ui/help-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { listChannels, listRefSeasonality } from "@/lib/channels";
import {
  useFieldValidation,
  type ValidationRules,
} from "@/lib/use-field-validation";

import type {
  Channel,
  ProjectSKUChannelCreate,
  RefSeasonality,
} from "@/types/api";

const NO_SEASONALITY = "__none__";

/**
 * Состояние формы как одна строковая структура (Decimal как string,
 * совместимо с PSC types и Pydantic Decimal валидацией на backend).
 */
export interface ChannelFormState {
  channel_id: string;
  launch_year: string;
  launch_month: string;
  nd_target: string;
  nd_ramp_months: string;
  offtake_target: string;
  channel_margin: string;
  promo_discount: string;
  promo_share: string;
  shelf_price_reg: string;
  logistics_cost_per_kg: string;
  seasonality_profile_id: string; // "" или число как строка
}

export const EMPTY_CHANNEL_FORM: ChannelFormState = {
  channel_id: "",
  launch_year: "1",
  launch_month: "1",
  nd_target: "0.5",
  nd_ramp_months: "12",
  offtake_target: "10",
  channel_margin: "0.4",
  promo_discount: "0.3",
  promo_share: "1.0",
  shelf_price_reg: "100",
  logistics_cost_per_kg: "8",
  seasonality_profile_id: "",
};

/** Конвертирует form state в payload для POST/PATCH PSC. */
export function toPscPayload(
  state: ChannelFormState,
): ProjectSKUChannelCreate {
  return {
    channel_id: Number(state.channel_id),
    launch_year: Number(state.launch_year) || 1,
    launch_month: Number(state.launch_month) || 1,
    nd_target: state.nd_target,
    nd_ramp_months: Number(state.nd_ramp_months),
    offtake_target: state.offtake_target,
    channel_margin: state.channel_margin,
    promo_discount: state.promo_discount,
    promo_share: state.promo_share,
    shelf_price_reg: state.shelf_price_reg,
    logistics_cost_per_kg: state.logistics_cost_per_kg,
    seasonality_profile_id:
      state.seasonality_profile_id === ""
        ? null
        : Number(state.seasonality_profile_id),
  };
}

type FormField = keyof ChannelFormState;

const CHANNEL_FORM_RULES: ValidationRules<FormField> = {
  channel_id: { required: true, message: "Выберите канал" },
  launch_year: { required: true, numeric: true, min: 1, max: 10 },
  launch_month: { required: true, numeric: true, min: 1, max: 12 },
  nd_target: { required: true, numeric: true, min: 0, max: 1 },
  nd_ramp_months: { required: true, numeric: true, min: 1, max: 36 },
  offtake_target: { required: true, numeric: true, min: 0 },
  shelf_price_reg: { required: true, numeric: true, min: 0 },
  channel_margin: { required: true, numeric: true, min: 0, max: 1 },
  promo_discount: { required: true, numeric: true, min: 0, max: 1 },
  promo_share: { required: true, numeric: true, min: 0, max: 1 },
  logistics_cost_per_kg: { required: true, numeric: true, min: 0 },
};

interface ChannelFormProps {
  state: ChannelFormState;
  onChange: (next: ChannelFormState) => void;
  /** Список ID каналов которые уже привязаны (исключаются из dropdown).
   *  Передавай только при create. При edit оставляй пустым. */
  excludeChannelIds?: number[];
  /** При edit channel_id не меняется — Select disabled. */
  channelLocked?: boolean;
  disabled?: boolean;
  /** Ref to validate function — parent can call before submit. */
  onValidate?: (validateAll: () => boolean) => void;
}

export function ChannelForm({
  state,
  onChange,
  excludeChannelIds = [],
  channelLocked = false,
  disabled = false,
  onValidate,
}: ChannelFormProps) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [seasonality, setSeasonality] = useState<RefSeasonality[]>([]);
  const { errors, validateOne, validateAll, clearError } =
    useFieldValidation<FormField>(CHANNEL_FORM_RULES);

  // Expose validateAll to parent (dialogs call before submit)
  useEffect(() => {
    if (onValidate) {
      onValidate(() => validateAll(state));
    }
  }, [onValidate, validateAll, state]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listChannels(), listRefSeasonality()])
      .then(([ch, sn]) => {
        if (cancelled) return;
        setChannels(ch);
        setSeasonality(sn);
      })
      .catch(() => {
        /* без справочников форма всё ещё работает с уже выбранным channel_id */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const excluded = new Set(excludeChannelIds);
  const availableChannels = channels.filter(
    (c) => !excluded.has(c.id) || String(c.id) === state.channel_id,
  );

  function update<K extends keyof ChannelFormState>(
    key: K,
    value: ChannelFormState[K],
  ) {
    onChange({ ...state, [key]: value });
    clearError(key);
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="channel_id">Канал *</Label>
        <Select
          value={state.channel_id}
          onValueChange={(v) => update("channel_id", v ?? "")}
          disabled={disabled || channelLocked}
        >
          <SelectTrigger id="channel_id">
            <SelectValue placeholder="Выберите канал" />
          </SelectTrigger>
          <SelectContent>
            {availableChannels.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.code} — {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {availableChannels.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Все каналы уже привязаны к этому SKU.
          </p>
        )}
      </div>

      {/* === Launch lag (D-13): per канал, не per SKU === */}
      <div className="rounded-md border border-dashed p-3">
        <p className="mb-2 text-xs text-muted-foreground">
          Launch lag — месяц старта продаж канала. До этого периода
          pipeline обнуляет ND/offtake (продаж нет). Excel хранит per
          (SKU × Channel) — TT/E-COM каналы обычно запускаются раньше
          HM/SM/MM. По умолчанию Y1 Jan = с самого начала проекта.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="launch_year">Год запуска (1-10)</Label>
            <Input
              id="launch_year"
              type="number"
              min="1"
              max="10"
              step="1"
              value={state.launch_year}
              onChange={(e) => update("launch_year", e.target.value)}
              onBlur={() => validateOne("launch_year", state.launch_year)}
              aria-invalid={!!errors.launch_year}
              disabled={disabled}
            />
            <FieldError error={errors.launch_year} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="launch_month" className="flex items-center gap-1.5">
              Месяц запуска (1-12)
              <HelpButton help="channel.launch_month" />
            </Label>
            <Input
              id="launch_month"
              type="number"
              min="1"
              max="12"
              step="1"
              value={state.launch_month}
              onChange={(e) => update("launch_month", e.target.value)}
              onBlur={() => validateOne("launch_month", state.launch_month)}
              aria-invalid={!!errors.launch_month}
              disabled={disabled}
            />
            <FieldError error={errors.launch_month} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="nd_target" className="flex items-center gap-1.5">
            Числ. дистрибуция (доля)
            <HelpButton help="channel.nd_target" />
          </Label>
          <Input
            id="nd_target"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.nd_target}
            onChange={(e) => update("nd_target", e.target.value)}
            onBlur={() => validateOne("nd_target", state.nd_target)}
            aria-invalid={!!errors.nd_target}
            disabled={disabled}
          />
          <FieldError error={errors.nd_target} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="nd_ramp_months" className="flex items-center gap-1.5">
            Рамп-ап, мес.
            <HelpButton help="channel.nd_ramp_months" />
          </Label>
          <Input
            id="nd_ramp_months"
            type="number"
            min="1"
            max="36"
            value={state.nd_ramp_months}
            onChange={(e) => update("nd_ramp_months", e.target.value)}
            onBlur={() => validateOne("nd_ramp_months", state.nd_ramp_months)}
            aria-invalid={!!errors.nd_ramp_months}
            disabled={disabled}
          />
          <FieldError error={errors.nd_ramp_months} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="offtake_target" className="flex items-center gap-1.5">
            Офтейк (ед./точка/мес.)
            <HelpButton help="channel.offtake_target" />
          </Label>
          <Input
            id="offtake_target"
            type="number"
            step="0.01"
            min="0"
            value={state.offtake_target}
            onChange={(e) => update("offtake_target", e.target.value)}
            onBlur={() => validateOne("offtake_target", state.offtake_target)}
            aria-invalid={!!errors.offtake_target}
            disabled={disabled}
          />
          <FieldError error={errors.offtake_target} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="shelf_price_reg" className="flex items-center gap-1.5">
            Цена полки (с НДС), ₽/ед.
            <HelpButton help="channel.shelf_price_reg" />
          </Label>
          <Input
            id="shelf_price_reg"
            type="number"
            step="0.01"
            min="0"
            value={state.shelf_price_reg}
            onChange={(e) => update("shelf_price_reg", e.target.value)}
            onBlur={() => validateOne("shelf_price_reg", state.shelf_price_reg)}
            aria-invalid={!!errors.shelf_price_reg}
            disabled={disabled}
          />
          <FieldError error={errors.shelf_price_reg} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <Label htmlFor="channel_margin" className="flex items-center gap-1.5">
            Маржа канала (доля)
            <HelpButton help="channel.channel_margin" />
          </Label>
          <Input
            id="channel_margin"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.channel_margin}
            onChange={(e) => update("channel_margin", e.target.value)}
            onBlur={() => validateOne("channel_margin", state.channel_margin)}
            aria-invalid={!!errors.channel_margin}
            disabled={disabled}
          />
          <FieldError error={errors.channel_margin} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="promo_discount" className="flex items-center gap-1.5">
            Промо-скидка (доля)
            <HelpButton help="channel.promo_discount" />
          </Label>
          <Input
            id="promo_discount"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.promo_discount}
            onChange={(e) => update("promo_discount", e.target.value)}
            onBlur={() => validateOne("promo_discount", state.promo_discount)}
            aria-invalid={!!errors.promo_discount}
            disabled={disabled}
          />
          <FieldError error={errors.promo_discount} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="promo_share" className="flex items-center gap-1.5">
            Доля промо (доля)
            <HelpButton help="channel.promo_share" />
          </Label>
          <Input
            id="promo_share"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.promo_share}
            onChange={(e) => update("promo_share", e.target.value)}
            onBlur={() => validateOne("promo_share", state.promo_share)}
            aria-invalid={!!errors.promo_share}
            disabled={disabled}
          />
          <FieldError error={errors.promo_share} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="logistics_cost_per_kg">Логистика, ₽/кг</Label>
          <Input
            id="logistics_cost_per_kg"
            type="number"
            step="0.01"
            min="0"
            value={state.logistics_cost_per_kg}
            onChange={(e) => update("logistics_cost_per_kg", e.target.value)}
            onBlur={() =>
              validateOne("logistics_cost_per_kg", state.logistics_cost_per_kg)
            }
            aria-invalid={!!errors.logistics_cost_per_kg}
            disabled={disabled}
          />
          <FieldError error={errors.logistics_cost_per_kg} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="seasonality_profile_id">Сезонность</Label>
          <Select
            value={
              state.seasonality_profile_id === ""
                ? NO_SEASONALITY
                : state.seasonality_profile_id
            }
            onValueChange={(v) =>
              update(
                "seasonality_profile_id",
                v === null || v === NO_SEASONALITY ? "" : v,
              )
            }
            disabled={disabled}
          >
            <SelectTrigger id="seasonality_profile_id">
              <SelectValue placeholder="Без сезонности" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_SEASONALITY}>Без сезонности</SelectItem>
              {seasonality.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.profile_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}
