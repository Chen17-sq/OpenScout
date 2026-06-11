// Client-side private notes (localStorage only — no server state, auth/cloud
// sync comes later). One free-text note per researcher slug — "我对这个人的判断".
// Same svelte-store-backed-by-localStorage idiom as watchlist.ts.

import { browser } from '$app/environment';
import { writable, type Writable } from 'svelte/store';

const KEY = 'openscout:notes';

export type Note = { text: string; updated_at: string };
export type NotesMap = Record<string, Note>;

function readInitial(): NotesMap {
  if (typeof localStorage === 'undefined') return {};
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed == null || Array.isArray(parsed)) return {};
    const out: NotesMap = {};
    for (const [slug, v] of Object.entries(parsed as Record<string, unknown>)) {
      const n = v as Note;
      if (
        typeof n === 'object' &&
        n != null &&
        typeof n.text === 'string' &&
        typeof n.updated_at === 'string'
      ) {
        out[slug] = { text: n.text, updated_at: n.updated_at };
      }
    }
    return out;
  } catch {
    return {};
  }
}

export const notes: Writable<NotesMap> = writable(readInitial());

if (browser) {
  notes.subscribe((v) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(v));
    } catch {
      /* ignore quota errors */
    }
  });
}

export function saveNote(slug: string, text: string): void {
  notes.update((cur) => ({
    ...cur,
    [slug]: { text, updated_at: new Date().toISOString() },
  }));
}

export function deleteNote(slug: string): void {
  notes.update((cur) => {
    if (!(slug in cur)) return cur;
    const next = { ...cur };
    delete next[slug];
    return next;
  });
}
