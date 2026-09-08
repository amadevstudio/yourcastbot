import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(n: number) {
  if (n < 1024) return `${n} Б`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} КБ`;
  return `${(n / (1024 * 1024)).toFixed(1)} МБ`;
}

export function formatWhen(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRegisteredAt(value: string | null | undefined) {
  if (!value) return "дата неизвестна";
  const trimmed = value.trim();
  const hasTz = /Z$/i.test(trimmed) || /[+-]\d{2}:?\d{2}$/.test(trimmed);
  const iso = trimmed.includes("T") ? trimmed : trimmed.replace(" ", "T");
  const date = new Date(hasTz ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return "дата неизвестна";
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function centsToUsd(cents: number) {
  return (Number(cents || 0) / 100).toFixed(2);
}
