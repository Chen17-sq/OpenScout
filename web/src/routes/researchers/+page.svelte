<script lang="ts">
  import { t } from '$lib/i18n';
  import { roleLabel } from '$lib/api';

  let { data } = $props();
  const list = $derived(data.data?.items ?? []);
  const total = $derived(data.data?.total ?? 0);
  const limit = $derived(data.data?.limit ?? 100);
  const offset = $derived(data.data?.offset ?? 0);
  const hasNext = $derived(offset + list.length < total);
  const hasPrev = $derived(offset > 0);

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };

  function pageUrl(newOffset: number): string {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(data.filters)) if (v) params.set(k, v);
    params.set('offset', String(newOffset));
    return `/researchers?${params.toString()}`;
  }
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('list.label')}</div>
    <div class="h">{$t('list.title')}</div>
    <div class="meta">{$t('list.metaTotal', { n: total.toLocaleString() })}</div>
  </div>

  <div class="filter-strip">
    <div class="group">
      <a href="/researchers" class:active={!data.filters.confidence && !data.filters.topic && !data.filters.country}>
        {$t('list.filterAll')}
      </a>
      <a href="/researchers?confidence=high" class:active={data.filters.confidence === 'high'}>
        {$t('list.filterHigh')}
      </a>
      <a href="/researchers?confidence=low" class:active={data.filters.confidence === 'low'}>
        {$t('list.filterLow')}
      </a>
    </div>
    <div class="group">
      <a href="/researchers?topic=embodied" class:active={data.filters.topic === 'embodied'}>
        {$t('list.filterEmbodied')}
      </a>
      <a href="/researchers?topic=world_models" class:active={data.filters.topic === 'world_models'}>
        {$t('list.filterWorld')}
      </a>
      <a href="/researchers?topic=ai4sci" class:active={data.filters.topic === 'ai4sci'}>
        {$t('list.filterAi4sci')}
      </a>
    </div>
    <div class="group">
      <a href="/researchers?country=CN" class:active={data.filters.country === 'CN'}>
        🇨🇳 {$t('list.filterChina')}
      </a>
      <a href="/researchers?country=US" class:active={data.filters.country === 'US'}>
        🇺🇸 {$t('list.filterUS')}
      </a>
    </div>
    <div class="group sort">
      <span class="sort-label">SORT</span>
      <a href={`?${withSort('papers', data.filters)}`} class:active={(data.filters.sort ?? 'papers') === 'papers'}>{$t('list.sortByPapers')}</a>
      <a href={`?${withSort('citations', data.filters)}`} class:active={data.filters.sort === 'citations'}>{$t('list.sortByCitations')}</a>
      <a href={`?${withSort('h_index', data.filters)}`} class:active={data.filters.sort === 'h_index'}>{$t('list.sortByH')}</a>
    </div>
  </div>

  <table class="board-table">
    <thead>
      <tr>
        <th>{$t('list.colName')}</th>
        <th>{$t('list.colRole')}</th>
        <th>{$t('list.colCountry')}</th>
        <th>{$t('list.colConfidence')}</th>
        <th>{$t('list.colTags')}</th>
        <th class="text-right">{$t('list.colCitations')}</th>
        <th class="text-right">{$t('list.colH')}</th>
        <th class="text-right">{$t('list.colPapers')}</th>
      </tr>
    </thead>
    <tbody>
      {#each list as r}
        <tr>
          <td>
            <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
            {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
          </td>
          <td class="font-mono text-xs uppercase tracking-wider text-n600">{roleLabel(r.current_role)}</td>
          <td class="font-mono text-xs">{r.country ? `${flag(r.country)} ${r.country}` : '—'}</td>
          <td>
            {#if r.confidence_level === 'high'}
              <span class="badge anchor">{$t('researcher.confHigh')}</span>
            {:else if r.confidence_level === 'medium'}
              <span class="badge">OpenAlex</span>
            {:else}
              <span class="badge" style="color:#737373;border-color:#a3a3a3">Auto</span>
            {/if}
          </td>
          <td class="tag-cell">
            {#if r.tags?.length}
              {#each r.tags.slice(0, 3) as tag}
                <a href={`/tags/${encodeURIComponent(tag.label)}`} class="mini-tag">{tag.label}</a>
              {/each}
            {:else}—{/if}
          </td>
          <td class="text-right font-mono">{(r.citation_count ?? 0).toLocaleString()}</td>
          <td class="text-right font-mono">{r.h_index ?? '—'}</td>
          <td class="text-right font-mono">{r.n_papers ?? 0}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  {#if hasNext || hasPrev}
    <nav class="pager">
      {#if hasPrev}
        <a href={pageUrl(Math.max(0, offset - limit))}>← prev</a>
      {:else}
        <span></span>
      {/if}
      <span class="info">
        {offset + 1}–{offset + list.length} of {total.toLocaleString()}
      </span>
      {#if hasNext}
        <a href={pageUrl(offset + limit)}>next →</a>
      {:else}
        <span></span>
      {/if}
    </nav>
  {/if}
</section>

<style>
  .pager {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 22px 28px;
    border-top: 1px solid var(--ink);
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }
  .pager a {
    color: var(--ink);
    text-decoration: none;
    padding: 4px 12px;
    border: 1px solid var(--ink);
  }
  .pager a:hover {
    background: var(--ink);
    color: var(--paper);
  }
  .pager .info {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    color: var(--n500);
    letter-spacing: 0.06em;
    text-transform: none;
  }
</style>

<script context="module" lang="ts">
  function withSort(s: string, filters: Record<string, string>): string {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) {
      if (v && k !== 'sort') params.set(k, v);
    }
    params.set('sort', s);
    return params.toString();
  }
</script>

<style>
  .filter-strip {
    display: flex;
    gap: 0;
    flex-wrap: wrap;
    border-bottom: 1px solid var(--ink);
  }
  .filter-strip .group {
    display: flex;
    gap: 0;
    padding: 10px 14px;
    border-right: 1px solid var(--ink);
  }
  .filter-strip .group:last-child {
    border-right: none;
  }
  .filter-strip a {
    display: inline-block;
    padding: 4px 10px;
    font-family: 'Inter', sans-serif;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--n600);
    text-decoration: none;
    text-transform: uppercase;
  }
  .filter-strip a:hover {
    background: var(--n100);
    color: var(--ink);
  }
  .filter-strip a.active {
    background: var(--ink);
    color: var(--paper);
  }
  .filter-strip .sort-label {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--n500);
    padding: 4px 10px 4px 0;
  }
  .tag-cell {
    max-width: 280px;
  }
  .mini-tag {
    display: inline-block;
    margin: 2px 4px 2px 0;
    padding: 1px 6px;
    font-family: 'Inter', sans-serif;
    font-size: 9.5px;
    font-weight: 600;
    color: var(--ink);
    border: 1px solid var(--n400);
    text-decoration: none;
  }
  .mini-tag:hover {
    background: var(--ink);
    color: var(--paper);
  }
</style>
