import { browser } from '$app/environment';
import { derived, writable, type Writable } from 'svelte/store';

import { translations, type Locale } from './translations';

const COOKIE_NAME = 'openscout_locale';
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function readCookieLocale(): Locale {
  if (!browser) return 'zh';
  const m = document.cookie.match(new RegExp(`${COOKIE_NAME}=(zh|en)`));
  return (m?.[1] as Locale) ?? 'zh';
}

export const locale: Writable<Locale> = writable(readCookieLocale());

if (browser) {
  locale.subscribe((v) => {
    document.cookie = `${COOKIE_NAME}=${v}; path=/; max-age=${COOKIE_MAX_AGE}; samesite=lax`;
    document.documentElement.lang = v === 'zh' ? 'zh-CN' : 'en';
  });
}

/**
 * Translation lookup. Use as `$t('nav.today')`.
 * Supports interpolation: `$t('list.metaTotal', { n: 42 })`.
 */
export const t = derived(locale, ($l) => {
  return (key: string, vars?: Record<string, string | number>): string => {
    const parts = key.split('.');
    let cur: unknown = translations[$l];
    for (const p of parts) {
      if (typeof cur !== 'object' || cur == null) return key;
      cur = (cur as Record<string, unknown>)[p];
    }
    if (typeof cur !== 'string') return key;
    if (!vars) return cur;
    return cur.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''));
  };
});

/** Set initial locale from server (called from +layout.svelte on hydrate). */
export function hydrateLocale(value: Locale | null | undefined): void {
  if (value === 'zh' || value === 'en') {
    locale.set(value);
  }
}
