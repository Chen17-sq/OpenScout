<script lang="ts">
  import { arxivUrl, blurb, roleLabel } from '$lib/api';

  let { data } = $props();
  const r = $derived(data.researcher);
  const firstAuthored = $derived(r.papers.filter((p) => p.position === 1));
  const coAuthored = $derived(r.papers.filter((p) => p.position !== 1));
</script>

<section>
  <div class="section-head">
    <div class="label">Researcher</div>
    <div class="h">{r.name_en}</div>
    <div class="meta">{r.name_zh ?? ''}</div>
  </div>

  <div class="px-7 py-6 grid grid-cols-3 gap-6 border-b border-ink">
    <div>
      <div class="font-mono text-[10px] uppercase tracking-widest text-n500 mb-1">Stage</div>
      <div class="font-display text-2xl">{roleLabel(r.current_role) || '—'}</div>
      {#if r.career_stage_year}
        <div class="font-mono text-xs text-n600 mt-1">Year {r.career_stage_year}</div>
      {/if}
    </div>
    <div>
      <div class="font-mono text-[10px] uppercase tracking-widest text-n500 mb-1">Affiliation</div>
      <div class="font-display text-xl leading-tight">
        {r.current_affiliation?.name ?? '—'}
        {#if r.current_affiliation?.name_zh}
          <div class="text-base font-serif text-n600">{r.current_affiliation.name_zh}</div>
        {/if}
      </div>
    </div>
    <div>
      <div class="font-mono text-[10px] uppercase tracking-widest text-n500 mb-1">Advisor</div>
      {#if r.advisor}
        <a class="font-display text-xl" href={`/researchers/${r.advisor.slug}`}>{r.advisor.name_en}</a>
      {:else}
        <div class="font-display text-xl">—</div>
      {/if}
    </div>
  </div>

  <div class="px-7 py-5 border-b border-ink flex flex-wrap gap-3 font-mono text-[11px] uppercase tracking-widest">
    {#if r.confidence_level === 'high'}
      <span class="badge anchor">Anchor</span>
    {:else if r.confidence_level === 'medium'}
      <span class="badge">S2 verified</span>
    {:else}
      <span class="badge">Auto-discovered</span>
    {/if}
    {#if r.homepage_url}
      <a class="badge" href={r.homepage_url} target="_blank" rel="noreferrer">homepage ↗</a>
    {/if}
    {#if r.twitter_handle}
      <a class="badge" href={`https://x.com/${r.twitter_handle}`} target="_blank" rel="noreferrer">@{r.twitter_handle}</a>
    {/if}
    {#if r.github_handle}
      <a class="badge" href={`https://github.com/${r.github_handle}`} target="_blank" rel="noreferrer">github</a>
    {/if}
    {#if r.email}
      <span class="badge">email available · login required</span>
    {/if}
  </div>

  {#if r.bio}
    <div class="px-7 py-5 border-b border-ink">
      <div class="font-mono text-[10px] uppercase tracking-widest text-n500 mb-2">Bio</div>
      <p class="font-serif text-base text-n700 italic leading-relaxed">{r.bio}</p>
    </div>
  {/if}

  <div class="section-head">
    <div class="label">Output</div>
    <div class="h">First-Author Papers</div>
    <div class="meta">{firstAuthored.length} of {r.papers.length} total</div>
  </div>

  {#if firstAuthored.length === 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">No first-author papers in our snapshot.</div>
      <div></div>
    </div>
  {:else}
    {#each firstAuthored as p, i}
      <article class="story-card">
        <div class="no">{String(i + 1).padStart(2, '0')}</div>
        <div>
          <a class="title" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.title}</a>
          <div class="by">
            {p.venue ?? 'arXiv'} · {p.published_at ?? 'TBD'}
            {#if p.topics.length}· {p.topics.join(' / ')}{/if}
          </div>
          {#if p.abstract}<div class="blurb">{blurb(p.abstract, 240)}</div>{/if}
        </div>
        <div class="right">
          <a class="v" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.arxiv_id ?? '—'}</a>
        </div>
      </article>
    {/each}
  {/if}

  {#if coAuthored.length}
    <div class="section-head">
      <div class="label">Output</div>
      <div class="h">Co-Authored</div>
      <div class="meta">{coAuthored.length} papers</div>
    </div>
    <table class="board-table">
      <thead>
        <tr>
          <th>Title</th>
          <th>Position</th>
          <th>Topics</th>
          <th>arXiv</th>
        </tr>
      </thead>
      <tbody>
        {#each coAuthored as p}
          <tr>
            <td><a href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.title}</a></td>
            <td class="font-mono text-xs">#{p.position}</td>
            <td class="font-mono text-xs">{p.topics.join(', ') || '—'}</td>
            <td class="font-mono text-xs"><a href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.arxiv_id ?? '—'}</a></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>
