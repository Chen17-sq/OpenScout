<script lang="ts">
  import { t } from '$lib/i18n';
  import { arxivUrl, roleLabel } from '$lib/api';

  let { data } = $props();
  const q = $derived(data.q);
  const results = $derived(data.results);
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('search.label')}</div>
    <div class="h">{$t('search.title')}</div>
    <div class="meta">{$t('search.forQuery', { q })}</div>
  </div>

  {#if !q}
    <div class="empty">{$t('search.emptyState')}</div>
  {:else if !results || (results.researchers.length === 0 && results.papers.length === 0)}
    <div class="empty">{$t('search.noResults')}</div>
  {:else}
    {#if results.researchers.length}
      <div class="section-head">
        <div class="label">Hits</div>
        <div class="h">{$t('search.researchers')}</div>
        <div class="meta">{results.researchers.length}</div>
      </div>
      <table class="board-table">
        <tbody>
          {#each results.researchers as r}
            <tr>
              <td>
                <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
                {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
              </td>
              <td class="font-mono text-xs">{roleLabel(r.current_role)}</td>
              <td class="font-mono text-xs">{r.country ?? '—'}</td>
              <td class="text-right font-mono">{(r.citation_count ?? 0).toLocaleString()}</td>
              <td class="text-right font-mono">h={r.h_index ?? '—'}</td>
              <td>
                {#each (r.tags ?? []).slice(0, 3) as tag}
                  <span class="badge">{tag.label}</span>
                {/each}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if results.matched_via_tags.length}
      <div class="section-head">
        <div class="label">Related</div>
        <div class="h">{$t('search.matchedViaTags')}</div>
        <div class="meta">{results.matched_via_tags.length}</div>
      </div>
      <table class="board-table">
        <tbody>
          {#each results.matched_via_tags as r}
            <tr>
              <td>
                <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
                {#if r.name_zh}<span class="text-n500"> · {r.name_zh}</span>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if results.papers.length}
      <div class="section-head">
        <div class="label">Papers</div>
        <div class="h">{$t('search.papers')}</div>
        <div class="meta">{results.papers.length}</div>
      </div>
      {#each results.papers as p, i}
        <article class="story-card">
          <div class="no">{String(i + 1).padStart(2, '0')}</div>
          <div>
            <a class="title" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.title}</a>
            <div class="by">arXiv:{p.arxiv_id} · {p.first_seen_at?.slice(0, 10) ?? '—'}</div>
          </div>
          <div></div>
        </article>
      {/each}
    {/if}
  {/if}
</section>

<style>
  .empty {
    padding: 80px 28px;
    text-align: center;
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n500);
    font-size: 15px;
  }
</style>
