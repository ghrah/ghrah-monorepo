import { ref } from "vue";

const STORAGE_KEY = "ghrah-font-scale";
const ALLOWED_SCALES = new Set(["0.9", "1", "1.1"]);

export const fontScale = ref("1");

function normalizeScale(value: string | null | undefined): string {
  return value && ALLOWED_SCALES.has(value) ? value : "1";
}

function applyScale(value: string) {
  document.documentElement.style.setProperty("--font-scale", value);
}

export function initFontScale() {
  fontScale.value = normalizeScale(localStorage.getItem(STORAGE_KEY));
  applyScale(fontScale.value);
}

export function setFontScale(value: string) {
  fontScale.value = normalizeScale(value);
  localStorage.setItem(STORAGE_KEY, fontScale.value);
  applyScale(fontScale.value);
}
