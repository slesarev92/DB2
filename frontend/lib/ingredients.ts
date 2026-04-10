/**
 * API обёртки для Ingredient catalog (B-04).
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./api";

import type { IngredientPriceRead, IngredientRead } from "@/types/api";

export function listIngredients(): Promise<IngredientRead[]> {
  return apiGet<IngredientRead[]>("/api/ingredients");
}

export function createIngredient(data: {
  name: string;
  unit?: string;
  category?: string;
}): Promise<IngredientRead> {
  return apiPost<IngredientRead>("/api/ingredients", data);
}

export function updateIngredient(
  id: number,
  data: { name?: string; unit?: string; category?: string },
): Promise<IngredientRead> {
  return apiPatch<IngredientRead>(`/api/ingredients/${id}`, data);
}

export function deleteIngredient(id: number): Promise<void> {
  return apiDelete<void>(`/api/ingredients/${id}`);
}

export function listIngredientPrices(
  ingredientId: number,
): Promise<IngredientPriceRead[]> {
  return apiGet<IngredientPriceRead[]>(
    `/api/ingredients/${ingredientId}/prices`,
  );
}

export function addIngredientPrice(
  ingredientId: number,
  data: { price_per_unit: string; effective_date: string; notes?: string },
): Promise<IngredientPriceRead> {
  return apiPost<IngredientPriceRead>(
    `/api/ingredients/${ingredientId}/prices`,
    data,
  );
}
