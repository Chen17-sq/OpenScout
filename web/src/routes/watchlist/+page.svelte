<script lang="ts">
  import { watchlist, toggle, compareSlots, addToCompare, COMPARE_MAX } from '$lib/watchlist';
  import { apiFetch, roleLabel } from '$lib/api';
  import { t } from '$lib/i18n';

  // Researcher payload returned by /researchers/{slug}. We only declare the
  // fields we actually use here — keep it loose vs the full type in [slug]/+page.ts.
  type R = {
    slug: string;
    name_en: string;
    name_zh: string | null;
    current_role: string | null;
    country: string | null;
    confidence_level: string;
    h_index: number | null;
    citation_count: number | null;
    investability_score_v2: number | null;
    tags: Array<{ label: string; label_zh?: string | null; type?: string; score?: number }>;
  };

  // ── data load ─────────────────────────────────────────────────────────────
  // We track per-slug load state so unstarring removes the row instantly without
  // refetching everything. `addedAt` (timestamp the slug first appeared in the
  // store) seeds the default sort "by date added".
  let researchers = $state<R[]>([]);
  let loading = $state(true);
  let addedAt = $state<Record<string, number>>({});
  let selected = $state<Set<string>>(new Set());

  // Filter state
  let signalFilter = $state<'all' | 'hot' | 'rising' | 'graduating'>('all');
  let countryFilter = $state<string>('all');
  let roleFilter = $state<string>('all');
  let sortKey = $state<'added' | 'score' | 'name'>('added');

  $effect(() => {
    const slugs = $watchlist;
    // remember first-seen times
    const now = Date.now();
    for (const s of slugs) {
      if (!(s in addedAt)) addedAt = { ...addedAt, [s]: now };
    }
    // drop selections for slugs that disappeared
    const next = new Set<string>();
    for (const s of selected) if (slugs.includes(s)) next.add(s);
    selected = next;

    loading = true;
    Promise.all(slugs.map((slug) => apiFetch<R>(`/researchers/${slug}`))).then((rs) => {
      researchers = rs.filter((x): x is R => !!x);
      loading = false;
    });
  });

  // ── derived: signal classification (same heuristic as Investment Lens) ───
  // Signal tags aren't a first-class API field on /researchers; we derive them
  // from {role, tag.type='signal'} so the chip filter is consistent with the
  // signal chips we render in the row. Keep cheap — recomputed per render.
  function signalsFor(r: R): Set<string> {
    const out = new Set<string>();
    const role = r.current_role ?? '';
    if (role === 'phd' || role === 'postdoc') out.add('rising');
    if (role === 'phd') out.add('graduating');
    if (role === 'incoming_ap') out.add('rising');
    // any signal-type tag → 🔥 hot
    if (r.tags?.some((tt) => tt.type === 'signal')) out.add('hot');
    // explicit high investability also counts as hot
    if ((r.investability_score_v2 ?? 0) >= 0.6) out.add('hot');
    return out;
  }

  // ── derived: filter + sort ───────────────────────────────────────────────
  const filtered = $derived.by<R[]>(() => {
    let list = researchers;
    if (signalFilter !== 'all') {
      list = list.filter((r) => signalsFor(r).has(signalFilter));
    }
    if (countryFilter !== 'all') {
      list = list.filter((r) => (r.country ?? '').toUpperCase() === countryFilter);
    }
    if (roleFilter !== 'all') {
      list = list.filter((r) => r.current_role === roleFilter);
    }
    return list;
  });

  const sorted = $derived.by<R[]>(() => {
    const copy = [...filtered];
    if (sortKey === 'added') {
      copy.sort((a, b) => (addedAt[a.slug] ?? 0) - (addedAt[b.slug] ?? 0));
    } else if (sortKey === 'score') {
      copy.sort((a, b) => (b.investability_score_v2 ?? 0) - (a.investability_score_v2 ?? 0));
    } else if (sortKey === 'name') {
      copy.sort((a, b) => (a.name_en ?? '').localeCompare(b.name_en ?? ''));
    }
    return copy;
  });

  // ── country / role options derived from the visible set ──────────────────
  const countries = $derived.by<string[]>(() => {
    const s = new Set<string>();
    for (const r of researchers) if (r.country) s.add(r.country.toUpperCase());
    return Array.from(s).sort();
  });
  const roles = $derived.by<string[]>(() => {
    const s = new Set<string>();
    for (const r of researchers) if (r.current_role) s.add(r.current_role);
    return Array.from(s).sort();
  });

  // ── visuals ──────────────────────────────────────────────────────────────
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

  // ── compare actions ──────────────────────────────────────────────────────
  function toggleSelect(slug: string) {
    const next = new Set(selected);
    if (next.has(slug)) next.delete(slug);
    else if (next.size < COMPARE_MAX) next.add(slug);
    selected = next;
  }

  function compareUrlFor(slugs: string[]): string {
    return `/compare?slugs=${slugs.map((s) => encodeURIComponent(s)).join(',')}`;
  }

  function compareSelectedUrl(): string {
    const chosen =
      selected.size > 0 ? sorted.filter((r) => selected.has(r.slug)).map((r) => r.slug) : [];
    return compareUrlFor(chosen.slice(0, COMPARE_MAX));
  }

  function compareAllUrl(): string {
    // first 3 in current sort order
    return compareUrlFor(sorted.slice(0, COMPARE_MAX).map((r) => r.slug));
  }

  function quickAddToCompare(slug: string) {
    addToCompare(slug);
  }
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('watchlist.label')}</div>
    <div class="h">{$t('watchlist.title')}</div>
    <div class="meta">
      {#if $watchlist.length}
        {$t('watchlist.metaCount', { n: $watchlist.length })}
      {:else}
        {$t('watchlist.metaEmpty')}
      {/if}
    </div>
  </div>

  {#if loading && researchers.length === 0 && $watchlist.length > 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">…</div>
      <div></div>
    </div>
  {:else if $watchlist.length === 0}
    <div class="story-card empty-card">
      <div class="big-star">★</div>
      <div>
        <div class="blurb">{$t('watchlist.emptyHint')}</div>
      </div>
      <div></div>
    </div>
  {:else}
    <div class="filters">
      <div class="filter-group">
        <span class="filt-lbl">{$t('watchlist.filterSignal')}</span>
        {#each [['all', 'filterAll'], ['hot', 'signalHot'], ['rising', 'signalRising'], ['graduating', 'signalGraduating']] as opt}
          <button
            type="button"
            class="chip"
            class:active={signalFilter === opt[0]}
            onclick={() => (signalFilter = opt[0] as typeof signalFilter)}
          >
            {$t(`watchlist.${opt[1]}`)}
          </button>
        {/each}
      </div>
      <div class="filter-group">
        <span class="filt-lbl">{$t('watchlist.filterCountry')}</span>
        <select bind:value={countryFilter} aria-label={$t('watchlist.filterCountry')}>
          <option value="all">{$t('watchlist.filterAll')}</option>
          {#each countries as cc}
            <option value={cc}>{flag(cc)} {cc}</option>
          {/each}
        </select>
      </div>
      <div class="filter-group">
        <span class="filt-lbl">{$t('watchlist.filterRole')}</span>
        <select bind:value={roleFilter} aria-label={$t('watchlist.filterRole')}>
          <option value="all">{$t('watchlist.filterAll')}</option>
          {#each roles as rl}
            <option value={rl}>{roleLabel(rl)}</option>
          {/each}
        </select>
      </div>
      <div class="filter-group right">
        <span class="filt-lbl">↕</span>
        <select bind:value={sortKey} aria-label="sort">
          <option value="added">{$t('watchlist.sortByAdded')}</option>
          <option value="score">{$t('watchlist.sortByScore')}</option>
          <option value="name">{$t('watchlist.sortByName')}</option>
        </select>
      </div>
    </div>

    <div class="action-bar">
      <div class="hint">{$t('watchlist.compareHint')}</div>
      <div class="actions">
        {#if selected.size >= 2}
          <a class="cmp-cta" href={compareSelectedUrl()}>
            {$t('watchlist.compareSelected', { n: selected.size })}
          </a>
        {:else if sorted.length >= 2}
          <a class="cmp-cta" href={compareAllUrl()}>{$t('watchlist.compareAll')}</a>
        {/if}
      </div>
    </div>

    <table class="board-table watchlist-board">
      <thead>
        <tr>
          <th class="cmpcol"></th>
          <th>Name</th>
          <th>Role</th>
          <th>Country</th>
          <th>Signals</th>
          <th>Topics</th>
          <th class="text-right">inv-v2</th>
          <th class="text-right">h</th>
          <th class="text-right">cites</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each sorted as r (r.slug)}
          {@const sigs = signalsFor(r)}
          {@const topicTags = (r.tags ?? [])
            .filter((tt) => !tt.type || tt.type === 'topic')
            .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
            .slice(0, 3)}
          <tr>
            <td class="cmpcol">
              <input
                type="checkbox"
                checked={selected.has(r.slug)}
                onchange={() => toggleSelect(r.slug)}
                disabled={!selected.has(r.slug) && selected.size >= COMPARE_MAX}
                aria-label="select for compare"
              />
            </td>
            <td>
              <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
              {#if r.name_zh}
                <span class="zh"> · {r.name_zh}</span>
              {/if}
            </td>
            <td class="mono">{roleLabel(r.current_role) || '—'}</td>
            <td class="mono">{r.country ? `${flag(r.country)} ${r.country}` : '—'}</td>
            <td>
              {#if sigs.has('hot')}<span class="sig">🔥</span>{/if}
              {#if sigs.has('rising')}<span class="sig">🚀</span>{/if}
              {#if sigs.has('graduating')}<span class="sig">🎓</span>{/if}
            </td>
            <td>
              {#each topicTags as tag}
                <a class="tag" href={`/tags/${encodeURIComponent(tag.label)}`}>{tag.label}</a>
              {/each}
            </td>
            <td class="text-right mono">
              {#if r.investability_score_v2 != null}
                <span class="score {scoreClass(r.investability_score_v2)}">
                  {r.investability_score_v2.toFixed(2)}
                </span>
              {:else}
                —
              {/if}
            </td>
            <td class="text-right mono">{r.h_index ?? '—'}</td>
            <td class="text-right mono">{(r.citation_count ?? 0).toLocaleString()}</td>
            <td class="row-actions">
              <button
                type="button"
                class="mini"
                onclick={() => quickAddToCompare(r.slug)}
                title="add to compare slots"
                disabled={$compareSlots.includes(r.slug) || $compareSlots.length >= COMPARE_MAX}
              >
                {#if $compareSlots.includes(r.slug)}✓{:else}➕{/if}
              </button>
              <button
                type="button"
                class="mini danger"
                onclick={() => toggle(r.slug)}
                title={$t('watchlist.removeOne')}
                aria-label={$t('watchlist.removeOne')}
              >✕</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  /* ── filter bar ──────────────────────────────────────────────────────── */
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    padding: 14px 24px;
    border-bottom: 1px solid var(--ink);
    background: var(--n100);
  }
  .filter-group {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .filter-group.right {
    margin-left: auto;
  }
  .filt-lbl {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--n500);
  }
  .filter-group select {
    background: var(--paper);
    border: 1px solid var(--ink);
    padding: 4px 8px;
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    color: var(--ink);
    cursor: pointer;
  }
  .chip {
    background: var(--paper);
    border: 1px solid var(--ink);
    padding: 4px 10px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: var(--ink);
    cursor: pointer;
  }
  .chip.active {
    background: var(--ink);
    color: var(--paper);
  }
  .chip:hover {
    background: var(--accent);
    color: var(--paper);
    border-color: var(--accent);
  }

  /* ── action bar (compare-all CTA) ─────────────────────────────────────── */
  .action-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 24px;
    border-bottom: 1px solid var(--ink);
  }
  .action-bar .hint {
    font-family: 'Lora', serif;
    font-style: italic;
    font-size: 12px;
    color: var(--n500);
  }
  .cmp-cta {
    display: inline-block;
    padding: 6px 14px;
    background: var(--ink);
    color: var(--paper);
    text-decoration: none;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    border: 1px solid var(--ink);
  }
  .cmp-cta:hover {
    background: var(--accent);
    border-color: var(--accent);
  }

  /* ── table ───────────────────────────────────────────────────────────── */
  .watchlist-board {
    font-family: 'Lora', serif;
    font-size: 14px;
  }
  .watchlist-board th {
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
  .watchlist-board td {
    padding: 14px;
    border-bottom: 1px solid var(--muted);
    vertical-align: middle;
  }
  .watchlist-board a {
    color: var(--ink);
    text-decoration: none;
    font-weight: 600;
  }
  .watchlist-board a:hover {
    color: var(--accent);
  }
  .watchlist-board .zh {
    color: var(--n500);
    font-family: 'Lora', serif;
    font-style: italic;
  }
  .mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--n600);
  }
  .text-right {
    text-align: right;
  }
  .cmpcol {
    width: 30px;
    text-align: center;
  }
  .cmpcol input[type='checkbox'] {
    accent-color: var(--accent);
    cursor: pointer;
  }
  .cmpcol input[type='checkbox']:disabled {
    cursor: not-allowed;
    opacity: 0.4;
  }
  .sig {
    font-size: 15px;
    margin-right: 4px;
  }
  .tag {
    display: inline-block;
    border: 1px solid var(--ink);
    padding: 2px 8px;
    margin-right: 4px;
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 600;
    text-decoration: none;
    color: var(--ink);
  }
  .tag:hover {
    background: var(--ink);
    color: var(--paper) !important;
  }
  .score {
    display: inline-block;
    padding: 2px 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
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
  .row-actions {
    text-align: right;
    white-space: nowrap;
  }
  .mini {
    background: var(--paper);
    border: 1px solid var(--n400);
    color: var(--n600);
    padding: 2px 8px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    margin-left: 4px;
  }
  .mini:hover:not(:disabled) {
    border-color: var(--ink);
    color: var(--ink);
  }
  .mini:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .mini.danger:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  /* ── empty state ─────────────────────────────────────────────────────── */
  .empty-card .big-star {
    font-family: 'Playfair Display', serif;
    font-size: 80px;
    color: var(--n400);
    text-align: center;
    line-height: 1;
  }
  .empty-card .blurb {
    font-family: 'Lora', serif;
    font-size: 16px;
    font-style: italic;
    color: var(--n700);
  }
</style>