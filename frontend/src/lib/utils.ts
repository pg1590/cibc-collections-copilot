import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const integer = new Intl.NumberFormat("en-CA");
const cad = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 });

export function formatCount(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? integer.format(value) : "—";
}

export function formatCad(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? cad.format(value) : "—";
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short" });
}

/** Render any API value as readable text without inventing anything. */
export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? integer.format(value) : String(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

/** Turns snake_case keys from the API into readable column labels. */
export function humanize(key: string): string {
  const text = key.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
