<script lang="ts">
  import { untrack } from 'svelte';
  import { notes } from '$lib/notes';
  import { apiFetch, blurb } from '$lib/api';
  import { t } from '$lib/i18n';

  // We only need the name fields from /researchers/{slug}.
  type R = { slug: string; name_en: string; name_zh: string | null };

  // slug → display name, resolved client-side (same idiom as /watchlist).
  // If the API is down or the slug is gone, we fall back to the raw slug.
  let names = $state<Record<string, string>>({});
  const requested = new Set<string>();

  $effect(() => {
    const slugs = Object.keys($notes);
    untrack(() => {
      for (const slug of slugs) {
        if (requested.has(slug)) continue;
        requested.add(slug);
        apiFetch<R>(`/researchers/${slug}`).then((r) => {
          if (r) {
            names = {
              ...names,
              [slug]: r.name_zh ? `${r.name_en} · ${r.name_zh}` : r.name_en,
            };
          }
        });
      }
    });
  });

  // Newest first.
  const entries = $derived(
    Object.entries($notes).sort((a, b) => b[1].updated_at.localeCompare(a[1].updated_at)),
  );

  function fmt(iso: string): string {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
</script>

<section>
  <div class="section-head">
    <div class="label">Notes</div>
    <div class="h">{$t('notes.overviewTitle')}</div>
    <div class="meta">{$t('notes.overviewMeta', { n: entries.length })}</div>
  </div>

  {#if entries.length === 0}
    <div class="story-card empty-card">
      <div class="big-mark">📝</div>
      <div>
        <div class="empty-blurb">{$t('notes.empty')}</div>
      </div>
      <div></div>
    </div>
  {:else}
    <table class="board-table notes-board">
      <thead>
        <tr>
          <th class="who-col">Researcher</th>
          <th>Note</th>
          <th class="text-right when-col">{$t('notes.lastEdited')}</th>
        </tr>
      </thead>
      <tbody>
        {#each entries as [slug, note] (slug)}
          <tr>
            <td class="who">
              <a href={`/researchers/${slug}`}>{names[slug] ?? slug}</a>
            </td>
            <td class="excerpt">{blurb(note.text, 200)}</td>
            <td class="mono text-right">{fmt(note.updated_at)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  .notes-board {
    font-family: 'Lora', serif;
    font-size: 14px;
  }
  .notes-board th {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: var(--n500);
    padding: 12px 14px;
    text-align: left;
    background: var(--n100);
    border-bottom: 1px solid var(--ink);
  }
  .notes-board td {
    padding: 14px;
    border-bottom: 1px solid var(--muted);
    vertical-align: top;
  }
  .who-col {
    width: 220px;
  }
  .when-col {
    width: 150px;
  }
  .who a {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 16px;
    color: var(--ink);
    text-decoration: none;
  }
  .who a:hover {
    color: var(--accent);
  }
  .excerpt {
    font-family: 'Lora', serif;
    font-style: italic;
    font-size: 14.5px;
    line-height: 1.6;
    color: var(--n700);
  }
  .mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n500);
    white-space: nowrap;
  }
  .text-right {
    text-align: right;
  }
  /* ── empty state ─────────────────────────────────────────────────────── */
  .empty-card .big-mark {
    font-size: 56px;
    text-align: center;
    line-height: 1;
  }
  .empty-blurb {
    font-family: 'Lora', serif;
    font-size: 16px;
    font-style: italic;
    color: var(--n700);
  }
</style>
