/**
 * C #16: Display labels + ordering для ChannelGroup и ChannelSourceType.
 * Источник истины enum-значений = backend `schemas/channel.py` (Literal types).
 */
import type { ChannelGroup, ChannelSourceType } from "@/types/api";

export const CHANNEL_GROUP_LABELS: Record<ChannelGroup, string> = {
  HM: "Гипермаркеты",
  SM: "Супермаркеты",
  MM: "Минимаркеты",
  TT: "Традиционная розница",
  E_COM: "E-Commerce",
  HORECA: "HoReCa",
  QSR: "QSR / Фастфуд",
  OTHER: "Прочее",
};

/**
 * Порядок отображения групп в UI (диалог выбора каналов, list).
 * Менять только при явном UX-запросе — клиент опирается на этот порядок.
 */
export const CHANNEL_GROUP_ORDER: ChannelGroup[] = [
  "HM",
  "SM",
  "MM",
  "TT",
  "E_COM",
  "HORECA",
  "QSR",
  "OTHER",
];

export const CHANNEL_SOURCE_TYPE_LABELS: Record<ChannelSourceType, string> = {
  nielsen: "Nielsen",
  tsrpt: "ЦРПТ",
  gis2: "2GIS",
  infoline: "Infoline",
  custom: "Кастомный",
};
