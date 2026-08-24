"use client";

import { useI18n } from "./provider";

/**
 * Convenience hook returning the translation function `t` plus the current
 * locale and setter. Usage:
 *
 *   const { t, locale } = useT();
 *   <p>{t("auth.title")}</p>
 */
export function useT() {
  const { t, locale, setLocale } = useI18n();
  return { t, locale, setLocale };
}
