import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: string;
  /** Дополнительный класс для value (например color) */
  valueClassName?: string;
  /** Подпись под value (например "Y1-Y10") */
  subtitle?: string;
}

/**
 * Универсальная карточка одного KPI.
 *
 * Label сверху маленьким, Value большим, опциональный subtitle внизу.
 * Цвет value задаётся через `valueClassName` (например
 * `text-green-600` / `text-red-600`).
 */
export function KpiCard({
  label,
  value,
  valueClassName,
  subtitle,
}: KpiCardProps) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className={cn("mt-1 text-xl font-semibold", valueClassName)}>
          {value}
        </p>
        {subtitle !== undefined && (
          <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
}
