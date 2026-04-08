import { Badge } from "@/components/ui/badge";

interface GoNoGoBadgeProps {
  value: boolean | null;
}

/**
 * Цветной badge для Go/No-Go решения проекта.
 *
 * - true  → GREEN ("GO")
 * - false → RED ("NO GO")
 * - null  → серый ("не рассчитан") — расчёт ещё не запускался
 */
export function GoNoGoBadge({ value }: GoNoGoBadgeProps) {
  if (value === null) {
    return <Badge variant="outline">не рассчитан</Badge>;
  }
  if (value) {
    return (
      <Badge className="border-transparent bg-green-600 text-white hover:bg-green-700">
        GO
      </Badge>
    );
  }
  return (
    <Badge className="border-transparent bg-red-600 text-white hover:bg-red-700">
      NO GO
    </Badge>
  );
}
