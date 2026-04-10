"use client";

/**
 * GateTimeline — горизонтальная шкала G0→G5 с текущей позицией (Phase 8.7).
 *
 * Visual representation of project gate stage progression.
 */

const GATES = ["G0", "G1", "G2", "G3", "G4", "G5"] as const;

const GATE_LABELS: Record<string, string> = {
  G0: "Идея",
  G1: "Концепция",
  G2: "Разработка",
  G3: "Тест",
  G4: "Запуск",
  G5: "Масштабирование",
};

export function GateTimeline({ currentGate }: { currentGate: string | null }) {
  const currentIndex = currentGate ? GATES.indexOf(currentGate as typeof GATES[number]) : -1;

  return (
    <div className="w-full">
      {/* Timeline bar */}
      <div className="relative flex items-center justify-between px-2">
        {/* Background line */}
        <div className="absolute left-6 right-6 top-1/2 h-0.5 -translate-y-1/2 bg-border" />
        {/* Progress line */}
        {currentIndex >= 0 && (
          <div
            className="absolute left-6 top-1/2 h-0.5 -translate-y-1/2 bg-primary transition-all"
            style={{
              width: `${(currentIndex / (GATES.length - 1)) * (100 - 6)}%`,
            }}
          />
        )}

        {/* Gate dots */}
        {GATES.map((gate, i) => {
          const isPast = i < currentIndex;
          const isCurrent = i === currentIndex;
          const isFuture = i > currentIndex || currentIndex < 0;

          return (
            <div key={gate} className="relative z-10 flex flex-col items-center gap-1">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full border-2 text-[10px] font-bold transition-colors ${
                  isCurrent
                    ? "border-primary bg-primary text-primary-foreground"
                    : isPast
                      ? "border-primary bg-primary/20 text-primary"
                      : isFuture
                        ? "border-border bg-background text-muted-foreground"
                        : ""
                }`}
              >
                {gate}
              </div>
              <span
                className={`text-[10px] whitespace-nowrap ${
                  isCurrent ? "font-semibold text-foreground" : "text-muted-foreground"
                }`}
              >
                {GATE_LABELS[gate]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
