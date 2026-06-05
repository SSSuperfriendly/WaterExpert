import { THEME_STORAGE_KEY, getElement } from "./base.js";

function getStoredTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // ignore storage failures
  }
}

function normalizeTheme(theme) {
  return theme === "dark" ? "dark" : "light";
}

function updateThemeToggle(theme) {
  const button = getElement("themeToggleButton");
  if (!button) {
    return;
  }
  const nextTheme = theme === "dark" ? "light" : "dark";
  button.textContent = nextTheme === "dark" ? "夜间" : "日间";
  button.setAttribute("aria-label", nextTheme === "dark" ? "切换到夜间模式" : "切换到日间模式");
  button.title = nextTheme === "dark" ? "切换到夜间模式" : "切换到日间模式";
}

export function applyTheme(theme) {
  const normalizedTheme = normalizeTheme(theme);
  document.documentElement.dataset.theme = normalizedTheme;
  updateThemeToggle(normalizedTheme);
  persistTheme(normalizedTheme);
}

export function initThemeToggle() {
  applyTheme(getStoredTheme() || "light");
  const button = getElement("themeToggleButton");
  if (!button || button.dataset.bound === "1") {
    return;
  }
  button.dataset.bound = "1";
  button.addEventListener("click", () => {
    const currentTheme = normalizeTheme(document.documentElement.dataset.theme);
    applyTheme(currentTheme === "dark" ? "light" : "dark");
  });
}
