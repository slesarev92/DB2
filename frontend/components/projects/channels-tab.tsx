"use client";

import { useState } from "react";

import { ChannelsPanel } from "@/components/projects/channels-panel";
import { SkuPanel } from "@/components/projects/sku-panel";
import { Card, CardContent } from "@/components/ui/card";

interface ChannelsTabProps {
  projectId: number;
}

/**
 * Таб "Каналы" в карточке проекта.
 *
 * Layout как в SkusTab: 2-column grid (sku list 1/3, channels panel 2/3).
 * SkuPanel переиспользован — selection state поднят сюда чтобы координировать
 * левую и правую панели.
 */
export function ChannelsTab({ projectId }: ChannelsTabProps) {
  const [selectedPskId, setSelectedPskId] = useState<number | null>(null);

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
      <div className="md:col-span-1">
        <SkuPanel
          projectId={projectId}
          selectedPskId={selectedPskId}
          onSelectPsk={setSelectedPskId}
        />
      </div>
      <div className="md:col-span-2">
        {selectedPskId !== null ? (
          <ChannelsPanel pskId={selectedPskId} />
        ) : (
          <Card>
            <CardContent className="pt-6 text-sm text-muted-foreground">
              Выберите SKU слева, чтобы настроить каналы дистрибуции.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
