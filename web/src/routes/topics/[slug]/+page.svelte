<script lang="ts">
  import { arxivUrl, blurb, roleLabel } from '$lib/api';

  let { data } = $props();
  const t = $derived(data.topic);
  const maxN = $derived(Math.max(1, ...t.trend_7d.map((d) => d.n)));
</script>

<section>
  <div class="section-head">
    <div class="label">Topic</div>
    <div class="h">{t.name}</div>
    <div class="meta">{t.name_zh ?? ''}</div>
  </div>
  {#if t.description}
    <div class="px-7 py-5 border-b border-ink">
      <p class="font-serif italic text-n700">{t.description}</p>
    </div>
  {/if}

  <div class="section-head">
    <div class="label">Trend</div>
    <div class="h">Past 7 Days</div>
    <div class="meta">new papers per day</div>
  </div>
  <div class="px-7 pt-7 pb-9">
    <div class="bars">
      {#each t.trend_7d as d}
        <div class="bar" style="height: {(d.n / maxN) * 100}%">
          <span class="value">{d.n}</span>
          <span class="label">{d.date.slice(5)}</span>
        </div>
      {/each}
    </div>
  </div>

  <div class="section-head">
    <div class="label">Roster</div>
    <div class="h">Top First-Authors</div>
    <div class="meta">{t.top_first_authors.length} researchers</div>
  </div>
  <table class="board-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Role</th>
        <th class="text-right">First-Author Papers</th>
      </tr>
    </thead>
    <tbody>
      {#each t.top_first_authors as r}
        <tr>
          <td>
            <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
            {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
          </td>
          <td class="font-mono text-xs uppercase tracking-wider text-n600">{roleLabel(r.current_role)}</td>
          <td class="text-right font-mono">{r.n_papers}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  <div class="section-head">
    <div class="label">Stream</div>
    <div class="h">Recent Papers</div>
    <div class="meta">latest 20</div>
  </div>
  {#each t.recent_papers as p, i}
    <article class="story-card">
      <div class="no">{String(i + 1).padStart(2, '0')}</div>
      <div>
        <a class="title" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.title}</a>
        <div class="by">{p.published_at ?? 'TBD'} · arXiv:{p.arxiv_id ?? '—'}</div>
        {#if p.abstract}<div class="blurb">{blurb(p.abstract, 240)}</div>{/if}
      </div>
      <div class="right"></div>
    </article>
  {/each}
</section>
