"use client";

import { useState } from "react";

import { BomPanel } from "@/components/projects/bom-panel";
import { SkuPanel } from "@/components/projects/sku-panel";
import { Card, CardContent } from "@/components/ui/card";

interface SkusTabProps {
  projectId: number;
}

/**
 * Комбинирующий компонент для таба "SKU и BOM" в карточке проекта.
 *
 * Layout: 2 колонки на md+ (sku list 1/3, bom panel 2/3), на mobile —
 * стек. Selection state PSK поднят сюда чтобы координировать левую и
 * правую панели.
 */
export function SkusTab({ projectId }: SkusTabProps) {
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
          <BomPanel pskId={selectedPskId} />
        ) : (
          <Card>
            <CardContent className="pt-6 text-sm text-muted-foreground">
              Выберите SKU слева, чтобы редактировать BOM и параметры
              себестоимости.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
