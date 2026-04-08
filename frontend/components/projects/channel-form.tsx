"use client";

import { useEffect, useState } from "react";

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

interface ChannelFormProps {
  state: ChannelFormState;
  onChange: (next: ChannelFormState) => void;
  /** Список ID каналов которые уже привязаны (исключаются из dropdown).
   *  Передавай только при create. При edit оставляй пустым. */
  excludeChannelIds?: number[];
  /** При edit channel_id не меняется — Select disabled. */
  channelLocked?: boolean;
  disabled?: boolean;
}

export function ChannelForm({
  state,
  onChange,
  excludeChannelIds = [],
  channelLocked = false,
  disabled = false,
}: ChannelFormProps) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [seasonality, setSeasonality] = useState<RefSeasonality[]>([]);

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

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="nd_target">ND target (доля)</Label>
          <Input
            id="nd_target"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.nd_target}
            onChange={(e) => update("nd_target", e.target.value)}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="nd_ramp_months">Ramp месяцев</Label>
          <Input
            id="nd_ramp_months"
            type="number"
            min="1"
            max="36"
            value={state.nd_ramp_months}
            onChange={(e) => update("nd_ramp_months", e.target.value)}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="offtake_target">Off-take target (ед./точка)</Label>
          <Input
            id="offtake_target"
            type="number"
            step="0.01"
            min="0"
            value={state.offtake_target}
            onChange={(e) => update("offtake_target", e.target.value)}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="shelf_price_reg">Shelf price рег., ₽/ед.</Label>
          <Input
            id="shelf_price_reg"
            type="number"
            step="0.01"
            min="0"
            value={state.shelf_price_reg}
            onChange={(e) => update("shelf_price_reg", e.target.value)}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-2">
          <Label htmlFor="channel_margin">Channel margin</Label>
          <Input
            id="channel_margin"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.channel_margin}
            onChange={(e) => update("channel_margin", e.target.value)}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="promo_discount">Promo discount</Label>
          <Input
            id="promo_discount"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.promo_discount}
            onChange={(e) => update("promo_discount", e.target.value)}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="promo_share">Promo share</Label>
          <Input
            id="promo_share"
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={state.promo_share}
            onChange={(e) => update("promo_share", e.target.value)}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="logistics_cost_per_kg">Logistics ₽/кг</Label>
          <Input
            id="logistics_cost_per_kg"
            type="number"
            step="0.01"
            min="0"
            value={state.logistics_cost_per_kg}
            onChange={(e) => update("logistics_cost_per_kg", e.target.value)}
            disabled={disabled}
          />
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
