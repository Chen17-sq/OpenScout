<script lang="ts">
  import { t } from '$lib/i18n';

  let { data } = $props();
  const list = $derived(data.data?.items ?? []);
  const total = $derived(data.data?.total ?? 0);
  const limit = $derived(data.data?.limit ?? 50);
  const offset = $derived(data.data?.offset ?? 0);
  const hasNext = $derived(offset + list.length < total);
  const hasPrev = $derived(offset > 0);

  const fmt = (v: number | null) => (v == null ? '—' : v.toFixed(2));

  /** Build /papers URL from current filters with overrides; '' removes a key. Resets offset. */
  function filterUrl(overrides: Record<string, string>): string {
    const merged: Record<string, string> = { ...data.filters, ...overrides };
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) if (v) params.set(k, v);
    const qs = params.toString();
    return qs ? `/papers?${qs}` : '/papers';
  }

  function pageUrl(newOffset: number): string {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(data.filters)) if (v) params.set(k, v);
    params.set('offset', String(newOffset));
    return `/papers?${params.toString()}`;
  }
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('papersList.label')}</div>
    <div class="h">{$t('papersList.title')}</div>
    <div class="meta">{$t('papersList.metaTotal', { n: total.toLocaleString() })}</div>
  </div>

  <div class="filter-strip">
    <div class="group">
      <a href={filterUrl({ topic: '' })} class:active={!data.filters.topic}>
        {$t('papersList.filterAll')}
      </a>
      <a href={filterUrl({ topic: 'embodied' })} class:active={data.filters.topic === 'embodied'}>
        {$t('papersList.filterEmbodied')}
      </a>
      <a href={filterUrl({ topic: 'world_models' })} class:active={data.filters.topic === 'world_models'}>
        {$t('papersList.filterWorld')}
      </a>
      <a href={filterUrl({ topic: 'ai4sci' })} class:active={data.filters.topic === 'ai4sci'}>
        {$t('papersList.filterAi4sci')}
      </a>
    </div>
    <div class="group">
      <a
        href={filterUrl({ has_code: data.filters.has_code === 'true' ? '' : 'true' })}
        class:active={data.filters.has_code === 'true'}
      >
        {$t('papersList.filterHasCode')}
      </a>
    </div>
    <div class="group sort">
      <span class="sort-label">SORT</span>
      <a
        href={filterUrl({ sort: 'work_score' })}
        class:active={(data.filters.sort || 'work_score') === 'work_score'}
      >
        {$t('papersList.sortByScore')}
      </a>
      <a href={filterUrl({ sort: 'date' })} class:active={data.filters.sort === 'date'}>
        {$t('papersList.sortByDate')}
      </a>
      <a href={filterUrl({ sort: 'citations' })} class:active={data.filters.sort === 'citations'}>
        {$t('papersList.sortByCitations')}
      </a>
      <a href={filterUrl({ sort: 'stars' })} class:active={data.filters.sort === 'stars'}>
        {$t('papersList.sortByStars')}
      </a>
    </div>
  </div>

  <table class="board-table">
    <thead>
      <tr>
        <th>{$t('papersList.colTitle')}</th>
        <th>{$t('papersList.colVenue')}</th>
        <th>{$t('papersList.colDate')}</th>
        <th>{$t('papersList.colTopics')}</th>
        <th class="text-right">{$t('papersList.colAuthors')}</th>
        <th class="text-right">{$t('papersList.colCitations')}</th>
        <th class="text-right">{$t('papersList.colStars')}</th>
        <th class="text-right">{$t('papersList.colScore')}</th>
      </tr>
    </thead>
    <tbody>
      {#if list.length === 0}
        <tr>
          <td colspan="8" class="empty-cell">{$t('papersList.empty')}</td>
        </tr>
      {/if}
      {#each list as p}
        <tr>
          <td class="title-cell">
            {#if p.arxiv_id}
              <a href={`/papers/${encodeURIComponent(p.arxiv_id)}`}>{p.title}</a>
            {:else}
              <span>{p.title}</span>
            {/if}
          </td>
          <td class="font-mono text-xs uppercase tracking-wider text-n600">{p.venue ?? '—'}</td>
          <td class="font-mono text-xs">{p.published_at ?? '—'}</td>
          <td class="tag-cell">
            {#if p.topics?.length}
              {#each p.topics.slice(0, 3) as slug}
                <a href={`/topics/${encodeURIComponent(slug)}`} class="mini-tag">{slug}</a>
              {/each}
            {:else}—{/if}
          </td>
          <td class="text-right font-mono">{p.n_authors ?? 0}</td>
          <td class="text-right font-mono">{(p.citation_count ?? 0).toLocaleString()}</td>
          <td class="text-right font-mono">{p.github_stars != null ? p.github_stars.toLocaleString() : '—'}</td>
          <td class="text-right">
            <span class="score-main">{fmt(p.work_score)}</span>
            <span class="pillar-mini">
              B {fmt(p.breakthrough_score)} · C {fmt(p.commercial_score)} · Z {fmt(p.buzz_score)}
            </span>
          </td>
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
  .title-cell {
    max-width: 420px;
  }
  .tag-cell {
    max-width: 220px;
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
  .score-main {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
  }
  .pillar-mini {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    color: var(--n500);
    white-space: nowrap;
  }
  .empty-cell {
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n400);
    text-align: center;
    padding: 32px 0;
  }
</style>
