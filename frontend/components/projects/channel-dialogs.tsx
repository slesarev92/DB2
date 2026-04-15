"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  ChannelForm,
  EMPTY_CHANNEL_FORM,
  toPscPayload,
  type ChannelFormState,
} from "@/components/projects/channel-form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api";
import { addChannelToPsk, updatePskChannel } from "@/lib/channels";

import type { ProjectSKUChannelRead } from "@/types/api";

// ============================================================
// Add dialog
// ============================================================

interface AddChannelDialogProps {
  pskId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** ID каналов которые уже привязаны — исключаются из dropdown. */
  excludeChannelIds: number[];
  onAdded: () => void;
}

export function AddChannelDialog({
  pskId,
  open,
  onOpenChange,
  excludeChannelIds,
  onAdded,
}: AddChannelDialogProps) {
  const [form, setForm] = useState<ChannelFormState>(EMPTY_CHANNEL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const validateRef = useRef<(() => boolean) | null>(null);

  // Reset при закрытии
  useEffect(() => {
    if (open) return;
    setForm(EMPTY_CHANNEL_FORM);
    setError(null);
    setSubmitting(false);
  }, [open]);

  const handleValidateReady = useCallback((fn: () => boolean) => {
    validateRef.current = fn;
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (validateRef.current && !validateRef.current()) return;
    setSubmitting(true);
    try {
      await addChannelToPsk(pskId, toPscPayload(form));
      toast.success("Канал привязан");
      onAdded();
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось привязать канал: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Привязать канал к SKU</DialogTitle>
          <DialogDescription>
            Параметры канала. После сохранения автоматически генерируется
            predict-слой (43 PeriodValue × 3 сценария — задача 2.5).
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <ChannelForm
            state={form}
            onChange={setForm}
            excludeChannelIds={excludeChannelIds}
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
              {submitting ? "Сохранение..." : "Привязать канал"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================
// Edit dialog
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
