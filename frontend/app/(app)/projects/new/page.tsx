"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { ApiError } from "@/lib/api";
import { createProject, listRefInflation } from "@/lib/projects";

import type { ProjectCreate, RefInflation } from "@/types/api";

const NO_INFLATION_VALUE = "__none__";

const DEFAULT_FORM: ProjectCreate = {
  name: "",
  start_date: new Date().toISOString().slice(0, 10),
  horizon_years: 10,
  wacc: "0.19",
  tax_rate: "0.20",
  wc_rate: "0.12",
  vat_rate: "0.20",
  currency: "RUB",
  inflation_profile_id: null,
};

export default function NewProjectPage() {
  const router = useRouter();
  const [form, setForm] = useState<ProjectCreate>(DEFAULT_FORM);
  const [profiles, setProfiles] = useState<RefInflation[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Загружаем профили инфляции для dropdown
  useEffect(() => {
    let cancelled = false;
    listRefInflation()
      .then((data) => {
        if (!cancelled) setProfiles(data);
      })
      .catch(() => {
        // Не блокирующая ошибка — без профилей форма всё ещё отправляется
        // (с inflation_profile_id = null).
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function update<K extends keyof ProjectCreate>(
    key: K,
    value: ProjectCreate[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await createProject(form);
      router.push(`/projects/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка создания");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle>Новый проект</CardTitle>
          <CardDescription>
            Заполните основные параметры. После создания будут автоматически
            добавлены 3 сценария (Base / Conservative / Aggressive).
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Название *</Label>
              <Input
                id="name"
                required
                minLength={1}
                maxLength={500}
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                disabled={submitting}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="start_date">Дата старта *</Label>
                <Input
                  id="start_date"
                  type="date"
                  required
                  value={form.start_date}
                  onChange={(e) => update("start_date", e.target.value)}
                  disabled={submitting}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="horizon_years">Горизонт, лет *</Label>
                <Input
                  id="horizon_years"
                  type="number"
                  required
                  min={1}
                  max={20}
                  value={form.horizon_years}
                  onChange={(e) =>
                    update("horizon_years", Number(e.target.value))
                  }
                  disabled={submitting}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="wacc" className="flex items-center gap-1.5">
                  Ставка дисконтирования (WACC)
                  <HelpButton help="project.wacc" />
                </Label>
                <Input
                  id="wacc"
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={form.wacc}
                  onChange={(e) => update("wacc", e.target.value)}
                  disabled={submitting}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="tax_rate" className="flex items-center gap-1.5">
                  Налог на прибыль
                  <HelpButton help="project.tax_rate" />
                </Label>
                <Input
                  id="tax_rate"
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={form.tax_rate}
                  onChange={(e) => update("tax_rate", e.target.value)}
                  disabled={submitting}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="wc_rate" className="flex items-center gap-1.5">
                  Working Capital ratio
                  <HelpButton help="project.wc_rate" />
                </Label>
                <Input
                  id="wc_rate"
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={form.wc_rate}
                  onChange={(e) => update("wc_rate", e.target.value)}
                  disabled={submitting}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="vat_rate" className="flex items-center gap-1.5">
                  VAT
                  <HelpButton help="project.vat_rate" />
                </Label>
                <Input
                  id="vat_rate"
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={form.vat_rate}
                  onChange={(e) => update("vat_rate", e.target.value)}
                  disabled={submitting}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="inflation_profile_id">Профиль инфляции</Label>
              <Select
                value={
                  form.inflation_profile_id === null
                    ? NO_INFLATION_VALUE
                    : String(form.inflation_profile_id)
                }
                onValueChange={(v) =>
                  update(
                    "inflation_profile_id",
                    v === NO_INFLATION_VALUE ? null : Number(v),
                  )
                }
                disabled={submitting}
              >
                <SelectTrigger id="inflation_profile_id">
                  <SelectValue placeholder="Выберите профиль" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_INFLATION_VALUE}>
                    Без инфляции
                  </SelectItem>
                  {profiles.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.profile_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {error !== null && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </CardContent>
          <CardFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push("/projects")}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Создаём..." : "Создать проект"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
