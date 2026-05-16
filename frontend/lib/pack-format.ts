/**
 * C #19: Тип упаковки SKU — справочник enum.
 *
 * Должен совпадать с PackFormat Literal в backend/app/schemas/sku.py
 * и с CHECK constraint ck_skus_format в БД.
 *
 * См. spec docs/superpowers/specs/2026-05-16-c19-pack-format-enum-design.md §4.
 */

export type PackFormat =
  | "ПЭТ"
  | "Стекло"
  | "Банка"
  | "Сашет"
  | "Стик"
  | "Пауч";

export const PACK_FORMAT_OPTIONS: readonly PackFormat[] = [
  "ПЭТ",
  "Стекло",
  "Банка",
  "Сашет",
  "Стик",
  "Пауч",
] as const;
