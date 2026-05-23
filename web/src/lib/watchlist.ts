// Client-side watchlist (localStorage only — no server state).
// Stores researcher slugs the user has starred.
//
// Also: a tiny `compareSlots` store — up to three researcher slugs the user
// has pinned for side-by-side viewing on /compare. Same shape, different key.

import { browser } from '$app/environment';
import { writable, type Writable } from 'svelte/store';

const KEY = 'openscout_watchlist_v1';
const COMPARE_KEY = 'openscout:compare';
export const COMPARE_MAX = 3;

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

// ── compare slots ────────────────────────────────────────────────────────────
// Up to COMPARE_MAX (3) slugs. Append-on-add, no-op if already present or full.

function readCompareInitial(): string[] {
  if (!browser) return [];
  try {
    const raw = localStorage.getItem(COMPARE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as unknown[]).filter((x): x is string => typeof x === 'string').slice(0, COMPARE_MAX);
  } catch {
    return [];
  }
}

export const compareSlots: Writable<string[]> = writable(readCompareInitial());

if (browser) {
  compareSlots.subscribe((v) => {
    try {
      localStorage.setItem(COMPARE_KEY, JSON.stringify(v));
    } catch {
      /* ignore quota errors */
    }
  });
}

export function addToCompare(slug: string): 'added' | 'present' | 'full' {
  let outcome: 'added' | 'present' | 'full' = 'added';
  compareSlots.update((cur) => {
    if (cur.includes(slug)) {
      outcome = 'present';
      return cur;
    }
    if (cur.length >= COMPARE_MAX) {
      outcome = 'full';
      return cur;
    }
    return [...cur, slug];
  });
  return outcome;
}

export function removeFromCompare(slug: string): void {
  compareSlots.update((cur) => cur.filter((x) => x !== slug));
}

export function clearCompare(): void {
  compareSlots.set([]);
}

export function setCompareAt(index: number, slug: string | null): void {
  compareSlots.update((cur) => {
    const next = cur.slice(0, COMPARE_MAX);
    while (next.length < COMPARE_MAX) next.push('');
    if (slug == null || slug === '') {
      next[index] = '';
    } else {
      // de-dupe: drop slug from anywhere else first
      for (let i = 0; i < next.length; i++) if (i !== index && next[i] === slug) next[i] = '';
      next[index] = slug;
    }
    return next.filter((x) => x);
  });
}
