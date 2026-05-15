/**
 * C #14 — Прямой URL `/projects/[id]/fine-tuning` для глубоких ссылок.
 *
 * Карточка проекта построена на табах внутри одного route (см.
 * `frontend/app/(app)/projects/[id]/page.tsx`); этот sub-route — алиас,
 * который перенаправляет на основной page с `?tab=fine-tuning`. Это
 * сохраняет единый UX (sidebar/keyboard shortcuts/AI-panel), не дублируя
 * композицию.
 */

import { redirect } from "next/navigation";

interface Props {
  params: { id: string };
}

export default function FineTuningRedirectPage({ params }: Props) {
  redirect(`/projects/${params.id}?tab=fine-tuning`);
}
