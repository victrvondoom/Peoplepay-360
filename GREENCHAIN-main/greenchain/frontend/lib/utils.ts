import { clsx, type ClassValue } from "clsx"
import type { LayoutStorage } from "react-resizable-panels"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const serverLayoutStorage: LayoutStorage = {
  getItem: () => null,
  setItem: () => {},
}

/** react-resizable-panels defaults to the global localStorage, which crashes server rendering. */
export const panelLayoutStorage: LayoutStorage =
  typeof window === "undefined" ? serverLayoutStorage : window.localStorage
