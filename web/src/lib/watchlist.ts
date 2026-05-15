// Client-side watchlist (localStorage only — no server state).
// Stores researcher slugs the user has starred.

import { browser } from '$app/environment';
import { writable, type Writable } from 'svelte/store';

const KEY = 'openscout_watchlist_v1';

function readInitial(): string[] {
  if (!browser) return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch {
    return [];
  }
}

export const watchlist: Writable<string[]> = writable(readInitial());

if (browser) {
  watchlist.subscribe((v) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(v));
    } catch {
      /* ignore quota errors */
    }
  });
}

export function toggle(slug: string): void {
  watchlist.update((cur) => {
    if (cur.includes(slug)) return cur.filter((x) => x !== slug);
    return [...cur, slug];
  });
}

export function has(slug: string, list: string[]): boolean {
  return list.includes(slug);
}
