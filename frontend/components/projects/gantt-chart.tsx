"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import type { RoadmapTask } from "@/types/api";

interface GanttChartProps {
  tasks: RoadmapTask[];
  projectStartDate?: string;
}

const STATUS_COLORS: Record<string, string> = {
  done: "#22c55e",
  in_progress: "#3b82f6",
  planned: "#94a3b8",
  blocked: "#ef4444",
};

// До 2026-05-15 поле статуса было свободным текстом — встречаются русские
// значения в существующих проектах. Маппим к каноническим ключам, чтобы
// Gantt раскрашивал корректно до того, как пользователь пересохранит задачу.
const STATUS_LEGACY_MAP: Record<string, string> = {
  "запланировано": "planned",
  "план": "planned",
  "в работе": "in_progress",
  "в процессе": "in_progress",
  "готово": "done",
  "выполнено": "done",
  "заблокировано": "blocked",
  "блок": "blocked",
};
function statusColor(raw: string): string {
  if (STATUS_COLORS[raw]) return STATUS_COLORS[raw];
  const legacy = STATUS_LEGACY_MAP[raw.trim().toLowerCase()];
  return STATUS_COLORS[legacy ?? "planned"];
}

function daysBetween(a: string, b: string): number {
  const msPerDay = 86400000;
  return Math.max(
    1,
    Math.round(
      (new Date(b).getTime() - new Date(a).getTime()) / msPerDay,
    ),
  );
}

/**
 * Gantt chart для roadmap_tasks (B-07).
 *
 * Горизонтальные бары: ось Y = задачи, ось X = дни от старта проекта.
 * Цвет по статусу: done (зелёный), in_progress (синий), planned (серый),
 * blocked (красный).
 */
export function GanttChart({ tasks, projectStartDate }: GanttChartProps) {
  // Filter tasks that have both start and end dates
  const validTasks = tasks.filter((t) => t.start_date && t.end_date);
  if (validTasks.length === 0) return null;

  // Find the earliest date as reference point
  const refDate =
    projectStartDate ??
    validTasks.reduce(
      (min, t) => (t.start_date! < min ? t.start_date! : min),
      validTasks[0].start_date!,
    );

  const chartData = validTasks.map((task) => {
    const offsetDays = daysBetween(refDate, task.start_date!);
    const durationDays = daysBetween(task.start_date!, task.end_date!);
    return {
      name: task.name.length > 25 ? task.name.slice(0, 22) + "..." : task.name,
      fullName: task.name,
      offset: offsetDays,
      duration: durationDays,
      status: task.status ?? "planned",
      owner: task.owner ?? "",
      startDate: task.start_date!,
      endDate: task.end_date!,
      // C #21: manual color override; null = fallback to statusColor
      color: task.color ?? null,
    };
  });

  const maxDay = Math.max(
    ...chartData.map((d) => d.offset + d.duration),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Диаграмма Ганта</CardTitle>
        <CardDescription>
          Визуализация roadmap: зелёный = выполнено, синий = в работе,
          серый = запланировано, красный = заблокировано.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer
          width="100%"
          height={validTasks.length * 40 + 50}
        >
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 5, right: 20, left: 120, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, maxDay + 5]}
              tickFormatter={(v: number) => `${v}d`}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={115}
              tick={{ fontSize: 11 }}
            />
            <Tooltip
              formatter={(value, name) => {
                if (name === "offset") return [null, null];
                return [`${value} дн.`, "Длительность"];
              }}
              labelFormatter={(_, payload) => {
                const item = payload?.[0]?.payload;
                if (!item) return "";
                return `${item.fullName}\n${item.startDate} → ${item.endDate}${item.owner ? ` (${item.owner})` : ""}`;
              }}
            />
            {/* Invisible offset bar */}
            <Bar dataKey="offset" stackId="a" fill="transparent" />
            {/* Visible duration bar */}
            <Bar dataKey="duration" stackId="a" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, i) => (
                // C #21: manual color override takes priority over status color
                <Cell key={i} fill={entry.color || statusColor(entry.status)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
