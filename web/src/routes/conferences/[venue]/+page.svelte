<script lang="ts">
  import { arxivUrl, blurb } from '$lib/api';

  let { data } = $props();
  const papers = $derived(data.data?.papers ?? []);
</script>

<section>
  <div class="section-head">
    <div class="label">Venue</div>
    <div class="h">{data.prefix}</div>
    <div class="meta">{papers.length} accepted papers</div>
  </div>

  {#each papers as p, i}
    {@const tier = p.venue?.toLowerCase().includes('oral') || p.venue?.toLowerCase().includes('spotlight') || p.venue?.toLowerCase().includes('best')}
    <article class="story-card">
      <div class="no" class:accent={tier}>{tier ? '✦' : String(i + 1).padStart(2, '0')}</div>
      <div>
        <a class="title" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.title}</a>
        <div class="by">
          {p.venue}
          {#if p.first_author}
            ·
            <a href={`/researchers/${p.first_author.slug}`}>
              {p.first_author.name_en}{p.first_author.name_zh ? ` · ${p.first_author.name_zh}` : ''}
            </a>
            (#1)
          {/if}
        </div>
        {#if p.abstract}<div class="blurb">{blurb(p.abstract, 280)}</div>{/if}
      </div>
      <div class="right">
        {#if p.arxiv_id}<a class="v" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.arxiv_id}</a>{/if}
      </div>
    </article>
  {/each}
</section>

<style>
  .story-card .no.accent {
    color: var(--accent);
    font-size: 32px;
  }
</style>
