<script lang="ts">
  // /investment — full Investment Lens browser.
  //
  // Visual language is shared with `$lib/InvestmentLens.svelte` (the home-page
  // 8-pick strip): newsprint chrome, three-pillar bars, score chip. But the
  // layout is a self-serve rank table with sticky filters + CSV export.
  //
  // All filter/sort/search/paginate work is client-side from a one-shot fetch
  // (the /investment/picks endpoint caps at limit=50; the page paginates
  // 30/page over the filtered subset). Server-side filtering can be added
  // later by widening +page.ts without breaking this component.

  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import type { InvestmentPick } from '$lib/api';
  import { paperUrl, roleLabel } from '$lib/api';
  import { t } from '$lib/i18n';
  import type { ResearcherMeta } from './+page';

  let { data } = $props();

  // ── data ──────────────────────────────────────────────────────────────
  const allPicks = $derived<InvestmentPick[]>(data.picks?.picks ?? []);
  const totalCount = $derived(allPicks.length);
  const metaBySlug = $derived<Record<string, ResearcherMeta>>(data.metaBySlug ?? {});

  // Read once for the initial value of `window_days`; subsequent changes
  // are driven by `applyWindow()` which does a URL-bound goto().
  // `untrack` keeps Svelte from warning about reading reactive `data` here.
  const _initialWindow = untrack(() => data.initialWindow ?? 30);

  // ── filter state ──────────────────────────────────────────────────────
  let country = $state<string>('all');
  let role = $state<string>('all');
  let signals = $state<Set<string>>(new Set());
  let window_days = $state<number>(_initialWindow);
  let topicQuery = $state<string>('');
  let sortKey = $state<'score' | 'name' | 'country' | 'role'>('score');
  let sortDir = $state<'asc' | 'desc'>('desc');
  let pageNum = $state<number>(1);
  const PAGE_SIZE = 30;

  // Window changes must reload the page (the API drives the candidate set).
  function applyWindow(w: number) {
    if (w === window_days) return;
    window_days = w;
    const params = new URLSearchParams(page.url.searchParams);
    params.set('window', String(w));
    goto(`/investment?${params.toString()}`, { keepFocus: true });
  }

  function toggleSignal(s: string) {
    const next = new Set(signals);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    signals = next;
    pageNum = 1;
  }

  function reset() {
    country = 'all';
    role = 'all';
    signals = new Set();
    topicQuery = '';
    sortKey = 'score';
    sortDir = 'desc';
    pageNum = 1;
  }

  function setSort(key: 'score' | 'name' | 'country' | 'role') {
    if (sortKey === key) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey = key;
      // score defaults to desc, everything else to asc.
      sortDir = key === 'score' ? 'desc' : 'asc';
    }
    pageNum = 1;
  }

  // ── signal classification ─────────────────────────────────────────────
  // The /investment/picks endpoint doesn't return explicit signal tags; we
  // derive them from {role, score percentile, reasons} so the chip filter is
  // self-consistent with what the user sees on the row.
  const scorePercentileCutoff = $derived(() => {
    if (allPicks.length === 0) return 0;
    const sorted = allPicks.map((p) => p.score).sort((a, b) => b - a);
    // top 20% = "🔥 高潜"
    const idx = Math.max(0, Math.floor(sorted.length * 0.2) - 1);
    return sorted[idx] ?? 0;
  });

  function pickSignals(pick: InvestmentPick): Set<string> {
    const cutoff = scorePercentileCutoff();
    const out = new Set<string>();
    if (pick.score >= cutoff && cutoff > 0) out.add('hot');
    if (pick.current_role === 'phd' || pick.current_role === 'postdoc') out.add('rising');
    if (pick.current_role === 'phd') out.add('graduating');
    if (pick.current_role === 'incoming_ap') out.add('incoming_ap');
    const reasons = pick.top_paper?.reasons ?? [];
    if (reasons.some((r) => /citation|S2|cites/i.test(r))) out.add('cited');
    return out;
  }

  // ── derived: filter + sort + paginate ─────────────────────────────────
  const filtered = $derived.by<InvestmentPick[]>(() => {
    let list = allPicks;
    if (country !== 'all') {
      list = list.filter((p) => (p.country ?? '').toUpperCase() === country);
    }
    if (role !== 'all') {
      list = list.filter((p) => p.current_role === role);
    }
    if (signals.size > 0) {
      list = list.filter((p) => {
        const sig = pickSignals(p);
        for (const want of signals) if (!sig.has(want)) return false;
        return true;
      });
    }
    if (topicQuery.trim()) {
      const q = topicQuery.trim().toLowerCase();
      list = list.filter((p) => {
        const tags = metaBySlug[p.slug]?.tags ?? [];
        if (tags.some((t) => t.label?.toLowerCase().includes(q))) return true;
        // Also match against paper title — feels natural for "topic" search.
        if (p.top_paper?.title?.toLowerCase().includes(q)) return true;
        return false;
      });
    }
    return list;
  });

  const sorted = $derived.by<InvestmentPick[]>(() => {
    const copy = [...filtered];
    const dir = sortDir === 'asc' ? 1 : -1;
    copy.sort((a, b) => {
      let av: string | number = 0;
      let bv: string | number = 0;
      if (sortKey === 'score') {
        av = a.score;
        bv = b.score;
      } else if (sortKey === 'name') {
        av = a.name_en || '';
        bv = b.name_en || '';
      } else if (sortKey === 'country') {
        av = a.country ?? '';
        bv = b.country ?? '';
      } else if (sortKey === 'role') {
        av = a.current_role ?? '';
        bv = b.current_role ?? '';
      }
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
    return copy;
  });

  const filteredCount = $derived(sorted.length);
  const pageCount = $derived(Math.max(1, Math.ceil(filteredCount / PAGE_SIZE)));
  const safePage = $derived(Math.min(Math.max(1, pageNum), pageCount));
  const offset = $derived((safePage - 1) * PAGE_SIZE);
  const paged = $derived(sorted.slice(offset, offset + PAGE_SIZE));
  const showingStart = $derived(filteredCount === 0 ? 0 : offset + 1);
  const showingEnd = $derived(Math.min(offset + PAGE_SIZE, filteredCount));

  // ── visuals (copied/echoed from InvestmentLens.svelte) ────────────────
  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };

  const pillarClass = (pick: InvestmentPick) => {
    if (!pick.top_paper) return 'pillar-buzz';
    const { breakthrough, commercial, buzz } = pick.top_paper;
    const max = Math.max(breakthrough, commercial, buzz);
    if (max === breakthrough) return 'pillar-breakthrough';
    if (max === commercial) return 'pillar-commercial';
    return 'pillar-buzz';
  };

  const positionLabel = (pos: number | null) => {
    if (!pos) return '';
    if (pos === 1) return $t('investment.posFirst');
    return `#${pos}`;
  };

  const truncate = (s: string | null | undefined, max = 110): string => {
    if (!s) return '';
    const clean = s.replace(/\s+/g, ' ').trim();
    return clean.length <= max ? clean : clean.slice(0, max - 1).trimEnd() + '…';
  };

  // ── CSV export ────────────────────────────────────────────────────────
  function csvEscape(v: string | number | null | undefined): string {
    if (v === null || v === undefined) return '';
    const s = String(v);
    if (s.includes(',') || s.includes('"') || s.includes('\n')) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  }

  function exportCsv() {
    const today = new Date().toISOString().slice(0, 10);
    const header = [
      'rank',
      'name_en',
      'name_zh',
      'country',
      'role',
      'score',
      'top_paper_title',
      'arxiv_id',
      'position',
      'breakthrough',
      'commercial',
      'buzz',
      'reasons',
    ];
    const rows = sorted.map((p, i) => [
      i + 1,
      p.name_en,
      p.name_zh ?? '',
      p.country ?? '',
      p.current_role ?? '',
      p.score.toFixed(3),
      p.top_paper?.title ?? '',
      p.top_paper?.arxiv_id ?? '',
      p.top_paper?.position ?? '',
      p.top_paper?.breakthrough?.toFixed(3) ?? '',
      p.top_paper?.commercial?.toFixed(3) ?? '',
      p.top_paper?.buzz?.toFixed(3) ?? '',
      (p.top_paper?.reasons ?? []).join(' | '),
    ]);
    const csv = [header, ...rows].map((row) => row.map(csvEscape).join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `investment_picks_${today}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // Reset to page 1 whenever non-pagination filter state changes — using a
  // tiny effect rather than threading it through every handler.
  let _prevKey = '';
  $effect(() => {
    const key = `${country}|${role}|${[...signals].sort().join(',')}|${topicQuery}|${sortKey}|${sortDir}`;
    if (key !== _prevKey) {
      _prevKey = key;
      pageNum = 1;
    }
  });

  // Sort header indicator.
  const sortIndicator = (key: typeof sortKey) =>
    sortKey === key ? (sortDir === 'desc' ? '▼' : '▲') : '';

  // Available country codes from the data — keep dropdown honest.
  const availableCountries = $derived.by(() => {
    const seen = new Set<string>();
    for (const p of allPicks) if (p.country) seen.add(p.country.toUpperCase());
    return ['all', ...[...seen].sort()];
  });

  onMount(() => {
    // Initialise window from URL if present (loader already set it server-side,
    // but this keeps client-side reactive var in sync after navigation).
    const w = parseInt(page.url.searchParams.get('window') ?? '30', 10);
    if (!Number.isNaN(w)) window_days = w;
  });
</script>

<svelte:head>
  <title>{$t('investment.pageTitle')} · OpenScout</title>
</svelte:head>

<section class="lens-page">
  <header class="hero">
    <div class="label">{$t('investment.pageLabel')}</div>
    <div class="h">{$t('investment.pageTitle')}</div>
    <div class="meta">
      {$t('investment.pageMeta')} · {window_days}d window
    </div>
  </header>

  <!-- Sticky filter bar -->
  <div class="filter-bar">
    <div class="filter-group">
      <span class="g-label">{$t('investment.filterCountry')}</span>
      <select bind:value={country}>
        {#each availableCountries as cc}
          <option value={cc}>
            {cc === 'all' ? $t('investment.countryAll') : `${flag(cc)} ${cc}`}
          </option>
        {/each}
      </select>
    </div>

    <div class="filter-group">
      <span class="g-label">{$t('investment.filterRole')}</span>
      <select bind:value={role}>
        <option value="all">{$t('investment.roleAll')}</option>
        <option value="phd">{$t('investment.rolePhd')}</option>
        <option value="postdoc">{$t('investment.rolePostdoc')}</option>
        <option value="incoming_ap">{$t('investment.roleIncomingAp')}</option>
        <option value="ap">{$t('investment.roleAp')}</option>
      </select>
    </div>

    <div class="filter-group">
      <span class="g-label">{$t('investment.filterWindow')}</span>
      <div class="radio-row">
        {#each [7, 30, 90, 365] as w}
          <button
            type="button"
            class="radio"
            class:active={window_days === w}
            onclick={() => applyWindow(w)}
          >
            {w}d
          </button>
        {/each}
      </div>
    </div>

    <div class="filter-group grow">
      <span class="g-label">{$t('investment.filterTopic')}</span>
      <input
        type="search"
        bind:value={topicQuery}
        placeholder={$t('investment.filterTopicPlaceholder')}
      />
    </div>

    <div class="filter-group">
      <button type="button" class="reset-btn" onclick={reset}>
        {$t('investment.filterReset')}
      </button>
      <button type="button" class="export-btn" onclick={exportCsv}>
        ⤓ {$t('investment.exportCsv')}
      </button>
    </div>
  </div>

  <div class="signal-bar">
    <span class="g-label">{$t('investment.filterSignal')}</span>
    {#each [['hot', 'signalHot'], ['rising', 'signalRising'], ['graduating', 'signalGraduating'], ['cited', 'signalCited'], ['incoming_ap', 'signalIncomingAp']] as pair}
      <button
        type="button"
        class="chip"
        class:active={signals.has(pair[0])}
        onclick={() => toggleSignal(pair[0])}
      >
        {$t(`investment.${pair[1]}`)}
      </button>
    {/each}
  </div>

  <!-- Rank table -->
  <table class="rank-table">
    <thead>
      <tr>
        <th class="num-col">{$t('investment.colRank')}</th>
        <th>
          <button type="button" class="sort-h" onclick={() => setSort('name')}>
            {$t('investment.colName')} <span class="ind">{sortIndicator('name')}</span>
          </button>
        </th>
        <th>
          <button type="button" class="sort-h" onclick={() => setSort('role')}>
            {$t('investment.colRole')} <span class="ind">{sortIndicator('role')}</span>
          </button>
        </th>
        <th>
          <button type="button" class="sort-h" onclick={() => setSort('country')}>
            {$t('investment.colCountry')} <span class="ind">{sortIndicator('country')}</span>
          </button>
        </th>
        <th class="bio-col">{$t('investment.colBio')}</th>
        <th>{$t('investment.colTopPaper')}</th>
        <th class="pillar-col">{$t('investment.colPillars')}</th>
        <th class="text-right">
          <button type="button" class="sort-h" onclick={() => setSort('score')}>
            {$t('investment.colScore')} <span class="ind">{sortIndicator('score')}</span>
          </button>
        </th>
      </tr>
    </thead>
    <tbody>
      {#if paged.length === 0}
        <tr>
          <td colspan="8" class="empty-cell">{$t('investment.empty')}</td>
        </tr>
      {:else}
        {#each paged as p, i}
          <tr class="rank-row {pillarClass(p)}">
            <td class="num-col">{String(offset + i + 1).padStart(2, '0')}</td>
            <td>
              <a class="name" href={`/researchers/${p.slug}`}>{p.name_en}</a>
              {#if p.name_zh}<span class="zh"> · {p.name_zh}</span>{/if}
            </td>
            <td class="font-mono small-cell">{roleLabel(p.current_role) || '—'}</td>
            <td class="font-mono small-cell">
              {p.country ? `${flag(p.country)} ${p.country}` : '—'}
            </td>
            <td class="bio-cell">{truncate(metaBySlug[p.slug]?.bio, 110) || '—'}</td>
            <td class="paper-cell">
              {#if p.top_paper}
                {#if p.top_paper.position}
                  <span class="pos">{positionLabel(p.top_paper.position)}</span>
                {/if}
                <a
                  class="paper-title"
                  href={paperUrl(p.top_paper.arxiv_id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {truncate(p.top_paper.title, 80)}
                </a>
                {#if p.top_paper.reasons.length}
                  <div class="why-row">
                    {#each p.top_paper.reasons.slice(0, 2) as r}
                      <span class="why-chip">{r}</span>
                    {/each}
                  </div>
                {/if}
              {:else}
                <span class="text-muted">—</span>
              {/if}
            </td>
            <td class="pillar-cell">
              {#if p.top_paper}
                <div class="mini-pillars">
                  <div class="mini-pillar">
                    <span class="pl">B</span>
                    <span class="bar"
                      ><span
                        class="fill b"
                        style="width: {p.top_paper.breakthrough * 100}%"
                      ></span></span
                    >
                  </div>
                  <div class="mini-pillar">
                    <span class="pl">C</span>
                    <span class="bar"
                      ><span
                        class="fill c"
                        style="width: {p.top_paper.commercial * 100}%"
                      ></span></span
                    >
                  </div>
                  <div class="mini-pillar">
                    <span class="pl">Z</span>
                    <span class="bar"
                      ><span
                        class="fill z"
                        style="width: {p.top_paper.buzz * 100}%"
                      ></span></span
                    >
                  </div>
                </div>
              {/if}
            </td>
            <td class="text-right score-cell">{p.score.toFixed(2)}</td>
          </tr>
        {/each}
      {/if}
    </tbody>
  </table>

  <!-- Pagination -->
  {#if filteredCount > 0}
    <nav class="pager">
      <button
        type="button"
        class="pager-btn"
        disabled={safePage <= 1}
        onclick={() => (pageNum = safePage - 1)}
      >
        {$t('investment.prev')}
      </button>
      <span class="info">
        {$t('investment.showingOf', {
          start: showingStart,
          end: showingEnd,
          total: filteredCount,
        })}
        {#if filteredCount !== totalCount}
          · ({totalCount} total)
        {/if}
      </span>
      <button
        type="button"
        class="pager-btn"
        disabled={safePage >= pageCount}
        onclick={() => (pageNum = safePage + 1)}
      >
        {$t('investment.next')}
      </button>
    </nav>
  {/if}

  <footer class="legend">
    <span><strong>B</strong> {$t('investment.legendB')}</span>
    <span><strong>C</strong> {$t('investment.legendC')}</span>
    <span><strong>Z</strong> {$t('investment.legendZ')}</span>
  </footer>
</section>

<style>
  /* ── layout ─────────────────────────────────────────────────────────── */
  .lens-page {
    border-top: 4px double var(--ink);
    border-bottom: 1px solid var(--ink);
    background: var(--paper);
  }
  .hero {
    padding: 26px 28px 18px;
    border-bottom: 1px solid var(--ink);
    display: grid;
    grid-template-columns: 170px 1fr auto;
    align-items: baseline;
    gap: 18px;
  }
  .label {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    color: var(--accent);
  }
  .h {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 34px;
    line-height: 1.05;
    color: var(--ink);
  }
  .meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n500);
    text-align: right;
  }

  /* ── sticky filter bar ─────────────────────────────────────────────── */
  .filter-bar {
    position: sticky;
    top: 0;
    z-index: 5;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0;
    padding: 10px 18px;
    background: var(--paper);
    border-bottom: 1px solid var(--ink);
  }
  .filter-group {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 14px;
    border-right: 1px solid var(--muted);
  }
  .filter-group.grow {
    flex: 1;
    min-width: 180px;
  }
  .filter-group:last-child {
    border-right: none;
    margin-left: auto;
  }
  .g-label {
    font-family: 'Inter', sans-serif;
    font-size: 9.5px;
    font-weight: 800;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--n500);
  }
  .filter-bar select,
  .filter-bar input[type='search'] {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    border: 1px solid var(--ink);
    background: var(--paper);
    color: var(--ink);
    padding: 4px 8px;
    outline: none;
  }
  .filter-bar input[type='search'] {
    width: 100%;
    min-width: 0;
  }
  .radio-row {
    display: flex;
    gap: 0;
  }
  .radio {
    border: 1px solid var(--ink);
    background: var(--paper);
    color: var(--ink);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 3px 9px;
    cursor: pointer;
  }
  .radio + .radio {
    border-left: none;
  }
  .radio:hover {
    background: var(--n100);
  }
  .radio.active {
    background: var(--ink);
    color: var(--paper);
  }
  .reset-btn,
  .export-btn {
    border: 1px solid var(--ink);
    background: var(--paper);
    color: var(--ink);
    font-family: 'Inter', sans-serif;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 5px 12px;
    cursor: pointer;
  }
  .reset-btn:hover {
    background: var(--n100);
  }
  .export-btn {
    background: var(--ink);
    color: var(--paper);
  }
  .export-btn:hover {
    background: var(--accent);
    border-color: var(--accent);
  }

  /* ── signal chips ───────────────────────────────────────────────────── */
  .signal-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 10px 28px;
    border-bottom: 1px solid var(--ink);
    background: var(--n100);
  }
  .chip {
    border: 1px solid var(--ink);
    background: var(--paper);
    color: var(--ink);
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    cursor: pointer;
  }
  .chip:hover {
    background: var(--n100);
  }
  .chip.active {
    background: var(--ink);
    color: var(--paper);
  }

  /* ── rank table ─────────────────────────────────────────────────────── */
  .rank-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'Lora', serif;
    font-size: 13px;
  }
  .rank-table thead th {
    background: var(--paper);
    border-bottom: 1px solid var(--ink);
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--n600);
    padding: 10px 12px;
    text-align: left;
  }
  .rank-table thead th.text-right {
    text-align: right;
  }
  .sort-h {
    background: none;
    border: 0;
    font: inherit;
    color: inherit;
    letter-spacing: inherit;
    text-transform: inherit;
    cursor: pointer;
    padding: 0;
  }
  .sort-h:hover {
    color: var(--ink);
  }
  .sort-h .ind {
    color: var(--accent);
    margin-left: 3px;
  }
  .rank-table tbody td {
    padding: 12px 12px;
    border-bottom: 1px solid var(--muted);
    vertical-align: top;
    color: var(--n700);
  }
  .rank-row:hover {
    background: var(--n100);
  }
  .num-col {
    width: 50px;
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 17px;
    color: var(--ink);
  }
  .name {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 15px;
    color: var(--ink);
    text-decoration: none;
  }
  .name:hover {
    color: var(--accent);
  }
  .zh {
    font-family: 'Lora', serif;
    font-size: 12px;
    color: var(--n500);
  }
  .small-cell {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n600);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    white-space: nowrap;
  }
  .bio-col {
    width: 22%;
  }
  .bio-cell {
    font-family: 'Lora', serif;
    font-size: 12px;
    color: var(--n600);
    line-height: 1.4;
  }
  .paper-cell {
    max-width: 280px;
  }
  .paper-title {
    color: var(--ink);
    text-decoration: underline;
    text-decoration-color: var(--n400);
    font-family: 'Lora', serif;
    font-size: 12.5px;
    line-height: 1.35;
  }
  .paper-title:hover {
    color: var(--accent);
  }
  .pos {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    background: var(--ink);
    color: var(--paper);
    padding: 1px 4px;
    margin-right: 6px;
    vertical-align: 2px;
  }
  .why-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }
  .why-chip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    border: 1px solid var(--n400);
    padding: 1px 5px;
    color: var(--n700);
    background: var(--paper);
  }
  .pillar-col,
  .pillar-cell {
    width: 150px;
  }
  .mini-pillars {
    display: grid;
    gap: 3px;
  }
  .mini-pillar {
    display: grid;
    grid-template-columns: 12px 1fr;
    align-items: center;
    gap: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
  }
  .pl {
    font-weight: 800;
    color: var(--n600);
  }
  .bar {
    height: 5px;
    background: var(--muted);
    display: block;
    position: relative;
  }
  .fill {
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
  }
  .fill.b {
    background: #6b3f9c;
  }
  .fill.c {
    background: #2f7a3a;
  }
  .fill.z {
    background: var(--accent);
  }
  .score-cell {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 700;
    color: var(--accent);
    white-space: nowrap;
  }
  .empty-cell {
    text-align: center;
    padding: 40px 20px;
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n500);
  }
  .text-muted {
    color: var(--n400);
  }
  .text-right {
    text-align: right;
  }
  .font-mono {
    font-family: 'JetBrains Mono', monospace;
  }

  /* ── pager + legend ─────────────────────────────────────────────────── */
  .pager {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 18px 28px;
    border-top: 1px solid var(--ink);
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }
  .pager-btn {
    background: var(--paper);
    color: var(--ink);
    border: 1px solid var(--ink);
    padding: 5px 14px;
    font: inherit;
    cursor: pointer;
  }
  .pager-btn:hover:not(:disabled) {
    background: var(--ink);
    color: var(--paper);
  }
  .pager-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
  .pager .info {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    color: var(--n500);
    letter-spacing: 0.06em;
    text-transform: none;
  }
  .legend {
    display: flex;
    gap: 22px;
    padding: 10px 28px;
    border-top: 1px solid var(--muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    color: var(--n600);
    background: var(--n100);
  }
  .legend strong {
    color: var(--ink);
    margin-right: 4px;
  }

  /* ── responsive ─────────────────────────────────────────────────────── */
  @media (max-width: 1100px) {
    .bio-col,
    .bio-cell {
      display: none;
    }
  }
  @media (max-width: 760px) {
    .hero {
      grid-template-columns: 1fr;
    }
    .meta {
      text-align: left;
    }
    .pillar-col,
    .pillar-cell {
      display: none;
    }
    .filter-group {
      border-right: none;
      padding: 6px 10px;
    }
    .filter-group:last-child {
      margin-left: 0;
    }
  }
</style>
