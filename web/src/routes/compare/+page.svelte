<script lang="ts">
  import { t } from '$lib/i18n';
  import { roleLabel, apiFetch, arxivUrl } from '$lib/api';
  import { compareSlots, COMPARE_MAX } from '$lib/watchlist';
  import { goto } from '$app/navigation';

  let { data } = $props();

  type Hit = {
    slug: string;
    name_en: string;
    name_zh: string | null;
    current_role: string | null;
  };

  // ── picker ────────────────────────────────────────────────────────────────
  // Three fixed slots; if URL has slugs we seed them, otherwise we read from
  // localStorage `openscout:compare`. Search box hits /search/?q=… (debounced).
  let slots = $state<string[]>(['', '', '']);
  let query = $state('');
  let hits = $state<Hit[]>([]);
  let activeSlot = $state<number>(0);
  let searching = $state(false);
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  let seeded = false;

  // Seed slots from URL slugs (preferred) or from localStorage (fallback).
  // Runs once on mount — reactivity-via-`data` is intentional one-shot.
  $effect(() => {
    if (seeded) return;
    seeded = true;
    const urlSlugs = data.slugs;
    if (urlSlugs.length > 0) {
      slots = [...urlSlugs, '', '', ''].slice(0, COMPARE_MAX);
    } else {
      const stored = $compareSlots;
      if (stored.length > 0) {
        slots = [...stored, '', '', ''].slice(0, COMPARE_MAX);
      }
    }
  });

  function runSearch(q: string) {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      const term = q.trim();
      if (!term) {
        hits = [];
        searching = false;
        return;
      }
      searching = true;
      const res = await apiFetch<{ researchers: Hit[] }>(
        `/search/?q=${encodeURIComponent(term)}`,
      );
      hits = (res?.researchers ?? []).slice(0, 8);
      searching = false;
    }, 180);
  }

  $effect(() => {
    runSearch(query);
  });

  function pick(slug: string) {
    const i = activeSlot;
    const next = [...slots];
    // de-dupe: drop slug from any other slot first
    for (let j = 0; j < next.length; j++) if (j !== i && next[j] === slug) next[j] = '';
    next[i] = slug;
    slots = next;
    // advance to next empty slot
    const nextEmpty = next.findIndex((s, j) => j > i && !s);
    activeSlot = nextEmpty >= 0 ? nextEmpty : i;
    query = '';
    hits = [];
  }

  function clearSlot(i: number) {
    const next = [...slots];
    next[i] = '';
    slots = next;
    activeSlot = i;
  }

  function startCompare() {
    const chosen = slots.filter((s) => s);
    if (chosen.length < 2) return;
    compareSlots.set(chosen);
    goto(`/compare?slugs=${chosen.map((s) => encodeURIComponent(s)).join(',')}`);
  }

  function resetAll() {
    slots = ['', '', ''];
    activeSlot = 0;
    query = '';
    hits = [];
  }

  // ── visuals ──────────────────────────────────────────────────────────────
  const rs = $derived(data.researchers);
  const showPicker = $derived(rs.length === 0);

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };

  function scoreClass(v: number | null): string {
    if (v == null) return '';
    if (v >= 0.7) return 'sc-hi';
    if (v >= 0.4) return 'sc-mid';
    return 'sc-lo';
  }

  function topFirstAuthor(r: (typeof rs)[number]) {
    const first = (r.papers ?? []).filter((p) => p.position === 1);
    if (first.length === 0) return null;
    // best-cited first
    return [...first].sort((a, b) => (b.citation_count ?? 0) - (a.citation_count ?? 0))[0];
  }

  // for the metric rows, find the max so we can highlight the winner
  function maxBy<T>(arr: T[], pick: (x: T) => number | null): number {
    let m = -Infinity;
    for (const x of arr) {
      const v = pick(x);
      if (v != null && v > m) m = v;
    }
    return m;
  }
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('compare.label')}</div>
    <div class="h">{$t('compare.title')}</div>
    <div class="meta">
      {#if rs.length >= 2}
        {$t('compare.meta')}
      {:else}
        {$t('compare.metaSingle')}
      {/if}
    </div>
  </div>

  {#if showPicker}
    <div class="picker">
      <div class="picker-head">
        <div class="picker-h">{$t('compare.pickerLabel')}</div>
        <div class="picker-hint">{$t('compare.pickerHint')}</div>
      </div>

      <div class="slots">
        {#each slots as slug, i}
          <div
            class="slot"
            class:filled={!!slug}
            class:active={activeSlot === i}
            role="button"
            tabindex="0"
            onclick={() => (activeSlot = i)}
            onkeydown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                activeSlot = i;
              }
            }}
          >
            <span class="slot-no">{i + 1}</span>
            <span class="slot-body">
              {#if slug}
                <span class="slot-name">{slug}</span>
              {:else}
                <span class="slot-empty">{$t('compare.pickerSlotEmpty')}</span>
              {/if}
            </span>
            {#if slug}
              <button
                type="button"
                class="slot-clear"
                onclick={(e) => {
                  e.stopPropagation();
                  clearSlot(i);
                }}
                title={$t('compare.clearSlot')}
              >✕</button>
            {/if}
          </div>
        {/each}
      </div>

      <div class="search-row">
        <input
          type="search"
          bind:value={query}
          placeholder={$t('compare.pickerSearch')}
          aria-label={$t('compare.pickerSearch')}
        />
        <button type="button" class="reset" onclick={resetAll}>{$t('compare.pickerReset')}</button>
        <button
          type="button"
          class="go"
          onclick={startCompare}
          disabled={slots.filter((s) => s).length < 2}
        >
          {$t('compare.pickerStart')} →
        </button>
      </div>

      {#if hits.length > 0}
        <ul class="hits">
          {#each hits as h}
            <li>
              <button type="button" onclick={() => pick(h.slug)}>
                <span class="hit-name">{h.name_en}</span>
                {#if h.name_zh}<span class="hit-zh"> · {h.name_zh}</span>{/if}
                <span class="hit-role">{roleLabel(h.current_role)}</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else if query.trim() && !searching}
        <div class="hits-empty">no matches</div>
      {/if}

      <div class="picker-foot">
        <a href="/watchlist">{$t('compare.backToWatchlist')}</a>
        <span class="cta-hint">{$t('compare.addToCompareCta')}</span>
      </div>
    </div>
  {:else}
    {@const n = rs.length}
    {@const maxCit = maxBy(rs, (r) => r.citation_count ?? 0)}
    {@const maxH = maxBy(rs, (r) => r.h_index ?? 0)}
    {@const maxW = maxBy(rs, (r) => r.works_count ?? 0)}
    {@const maxInv = maxBy(rs, (r) => r.investability_score_v2 ?? r.investability_score ?? 0)}

    <div class="cmp-grid" style:grid-template-columns={`repeat(${n}, 1fr)`}>
      {#each rs as r}
        <div class="cmp-cell">
          {#if r.photo_url}
            <img class="photo" src={r.photo_url} alt={r.name_en} />
          {/if}
          <h2 class="cmp-name">
            <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
            {#if r.name_zh}<span class="zh"> · {r.name_zh}</span>{/if}
          </h2>
          <div class="cmp-aff">{r.current_affiliation?.name ?? '—'}</div>
          <div class="cmp-role">
            {roleLabel(r.current_role)} · {r.country ? `${flag(r.country)} ${r.country}` : '—'}
          </div>
        </div>
      {/each}
    </div>

    <table class="cmp-table" style:grid-template-columns={`22% repeat(${n}, 1fr)`}>
      <tbody>
        <tr>
          <th>{$t('compare.rowInvestability')}</th>
          {#each rs as r}
            {@const v = r.investability_score_v2 ?? r.investability_score ?? null}
            <td class="big" class:winner={v != null && v === maxInv && maxInv > 0}>
              {#if v != null}
                <span class="score {scoreClass(v)}">{v.toFixed(3)}</span>
              {:else}—{/if}
            </td>
          {/each}
        </tr>
        <tr>
          <th>{$t('compare.rowCitation')}</th>
          {#each rs as r}
            <td class="big" class:winner={(r.citation_count ?? 0) === maxCit && maxCit > 0}>
              {(r.citation_count ?? 0).toLocaleString()}
            </td>
          {/each}
        </tr>
        <tr>
          <th>{$t('compare.rowH')}</th>
          {#each rs as r}
            <td class="big" class:winner={(r.h_index ?? 0) === maxH && maxH > 0}>
              {r.h_index ?? '—'}
            </td>
          {/each}
        </tr>
        <tr>
          <th>{$t('compare.rowWorks')}</th>
          {#each rs as r}
            <td class:winner={(r.works_count ?? 0) === maxW && maxW > 0}>
              {r.works_count ?? '—'}
            </td>
          {/each}
        </tr>
        <tr>
          <th>{$t('compare.rowSignals')}</th>
          {#each rs as r}
            <td>
              {#each (r.tags ?? []).filter((tt) => tt.type === 'signal').slice(0, 3) as tag}
                <span class="sig-tag">{tag.label_zh ?? tag.label}</span>
              {/each}
              {#if (r.tags ?? []).every((tt) => tt.type !== 'signal')}
                <span class="dim">—</span>
              {/if}
            </td>
          {/each}
        </tr>
        <tr>
          <th>{$t('compare.rowTopics')}</th>
          {#each rs as r}
            <td>
              {#each (r.tags ?? [])
                .filter((tt) => !tt.type || tt.type === 'topic')
                .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                .slice(0, 3) as tag}
                <a class="topic-tag" href={`/tags/${encodeURIComponent(tag.label)}`}>{tag.label}</a>
              {/each}
            </td>
          {/each}
        </tr>
        <tr>
          <th>{$t('compare.rowSignature')}</th>
          {#each rs as r}
            {@const top = topFirstAuthor(r) ?? r.signature_paper}
            <td>
              {#if top}
                <a class="paper" href={arxivUrl((top as { arxiv_id: string | null }).arxiv_id)} target="_blank" rel="noreferrer">
                  {top.title}
                </a>
                {#if 'citation_count' in top && (top as { citation_count?: number }).citation_count != null}
                  <div class="paper-meta">{(top as { citation_count: number }).citation_count.toLocaleString()} cites</div>
                {/if}
              {:else}—{/if}
            </td>
          {/each}
        </tr>
      </tbody>
    </table>
  {/if}
</section>

<style>
  /* ── picker ──────────────────────────────────────────────────────────── */
  .picker {
    padding: 22px 28px 28px;
    border-bottom: 4px solid var(--ink);
  }
  .picker-head {
    margin-bottom: 16px;
  }
  .picker-h {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 22px;
    color: var(--ink);
  }
  .picker-hint {
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n600);
    font-size: 13px;
    margin-top: 4px;
  }
  .slots {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    border: 1px solid var(--ink);
    margin-bottom: 16px;
  }
  .slot {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--paper);
    border: none;
    border-right: 1px solid var(--ink);
    padding: 14px 16px;
    text-align: left;
    cursor: pointer;
    min-height: 60px;
    position: relative;
  }
  .slot:last-child {
    border-right: none;
  }
  .slot.active {
    background: var(--n100);
    box-shadow: inset 0 0 0 2px var(--accent);
  }
  .slot.filled {
    background: var(--paper);
  }
  .slot-no {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 24px;
    color: var(--n400);
    line-height: 1;
  }
  .slot.filled .slot-no {
    color: var(--accent);
  }
  .slot-body {
    flex: 1;
    overflow: hidden;
  }
  .slot-name {
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink);
  }
  .slot-empty {
    font-family: 'Lora', serif;
    font-style: italic;
    font-size: 13px;
    color: var(--n400);
  }
  .slot-clear {
    background: transparent;
    border: 1px solid var(--n400);
    color: var(--n500);
    font-size: 11px;
    line-height: 1;
    padding: 2px 6px;
    cursor: pointer;
  }
  .slot-clear:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
  .search-row {
    display: flex;
    gap: 8px;
    align-items: stretch;
    margin-bottom: 8px;
  }
  .search-row input {
    flex: 1;
    background: var(--paper);
    border: 1px solid var(--ink);
    padding: 8px 12px;
    font-family: 'Lora', serif;
    font-size: 14px;
    color: var(--ink);
    outline: none;
  }
  .search-row input:focus {
    border-color: var(--accent);
  }
  .search-row .go,
  .search-row .reset {
    background: var(--ink);
    color: var(--paper);
    border: 1px solid var(--ink);
    padding: 8px 16px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    cursor: pointer;
  }
  .search-row .reset {
    background: var(--paper);
    color: var(--ink);
  }
  .search-row .go:disabled {
    background: var(--n400);
    border-color: var(--n400);
    cursor: not-allowed;
  }
  .search-row .go:not(:disabled):hover {
    background: var(--accent);
    border-color: var(--accent);
  }
  .hits {
    list-style: none;
    padding: 0;
    margin: 0;
    border: 1px solid var(--muted);
  }
  .hits li {
    border-bottom: 1px solid var(--muted);
  }
  .hits li:last-child {
    border-bottom: none;
  }
  .hits li button {
    display: flex;
    align-items: baseline;
    gap: 10px;
    width: 100%;
    text-align: left;
    background: var(--paper);
    border: none;
    padding: 10px 14px;
    cursor: pointer;
  }
  .hits li button:hover {
    background: var(--n100);
  }
  .hit-name {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    color: var(--ink);
    font-size: 15px;
  }
  .hit-zh {
    color: var(--n500);
    font-family: 'Lora', serif;
    font-style: italic;
  }
  .hit-role {
    margin-left: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n500);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .hits-empty {
    padding: 10px 14px;
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n500);
    font-size: 13px;
  }
  .picker-foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 18px;
    font-family: 'Lora', serif;
    font-size: 13px;
  }
  .picker-foot a {
    color: var(--ink);
    text-decoration: none;
    font-weight: 600;
  }
  .picker-foot a:hover {
    color: var(--accent);
  }
  .picker-foot .cta-hint {
    color: var(--n500);
    font-style: italic;
    font-size: 12px;
  }

  /* ── compare grid (header cards) ─────────────────────────────────────── */
  .cmp-grid {
    display: grid;
    border-bottom: 4px solid var(--ink);
  }
  .cmp-cell {
    padding: 22px 24px;
    border-right: 1px solid var(--ink);
  }
  .cmp-cell:last-child {
    border-right: none;
  }
  .cmp-name {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 32px;
    margin: 8px 0 6px;
    line-height: 1.05;
  }
  .cmp-name a {
    color: var(--ink);
    text-decoration: none;
  }
  .cmp-name a:hover {
    color: var(--accent);
  }
  .cmp-name .zh {
    color: var(--n500);
    font-weight: 700;
    font-size: 22px;
  }
  .cmp-aff {
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n700);
    font-size: 14px;
  }
  .cmp-role {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n500);
    margin-top: 6px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .photo {
    width: 64px;
    height: 64px;
    object-fit: cover;
    border: 2px solid var(--ink);
    display: block;
  }

  /* ── compare table ───────────────────────────────────────────────────── */
  .cmp-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'Lora', serif;
    font-size: 15px;
  }
  .cmp-table th {
    width: 22%;
    padding: 16px 22px;
    text-align: left;
    background: var(--n100);
    border-bottom: 1px solid var(--muted);
    font-family: 'Inter', sans-serif;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: var(--n500);
    vertical-align: top;
  }
  .cmp-table td {
    padding: 16px 22px;
    border-bottom: 1px solid var(--muted);
    border-left: 1px solid var(--muted);
    vertical-align: top;
  }
  .cmp-table td.big {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 28px;
    line-height: 1;
  }
  .cmp-table td.winner {
    background: var(--paper);
    color: var(--accent);
  }
  .cmp-table .dim {
    color: var(--n400);
  }
  .score {
    display: inline-block;
    padding: 3px 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    font-weight: 700;
    border: 1px solid var(--ink);
  }
  .score.sc-hi {
    background: var(--accent);
    color: var(--paper);
    border-color: var(--accent);
  }
  .score.sc-mid {
    background: var(--ink);
    color: var(--paper);
  }
  .score.sc-lo {
    color: var(--n500);
    border-color: var(--n400);
  }
  .sig-tag {
    display: inline-block;
    background: #fffaf0;
    border: 1px dashed #b8860b;
    color: #8a6300;
    padding: 2px 8px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    margin-right: 4px;
  }
  .topic-tag {
    display: inline-block;
    border: 1px solid var(--ink);
    padding: 2px 8px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: var(--ink);
    text-decoration: none;
    margin-right: 4px;
    margin-bottom: 4px;
  }
  .topic-tag:hover {
    background: var(--ink);
    color: var(--paper);
  }
  .paper {
    color: var(--ink);
    text-decoration: none;
    font-weight: 700;
    font-family: 'Playfair Display', serif;
    font-size: 16px;
    line-height: 1.3;
    display: inline-block;
  }
  .paper:hover {
    color: var(--accent);
  }
  .paper-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n500);
    margin-top: 4px;
  }
</style>
