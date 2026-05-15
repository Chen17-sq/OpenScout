<script lang="ts">
  import { roleLabel } from '$lib/api';

  let { data } = $props();
  const o = $derived(data.overview);
  const maxP = $derived(Math.max(1, ...(o?.series_7d.map((d) => d.papers) ?? [1])));
  const maxR = $derived(Math.max(1, ...(o?.series_7d.map((d) => d.researchers) ?? [1])));
</script>

{#if !o}
  <div class="story-card">
    <div></div>
    <div class="blurb">Stats unavailable.</div>
    <div></div>
  </div>
{:else}
  <div class="kpi-row">
    <div class="kpi">
      <div class="label">Researchers</div>
      <div class="num">{o.totals.researchers.toLocaleString()}</div>
      <div class="delta">all confidence levels</div>
    </div>
    <div class="kpi">
      <div class="label">Anchors</div>
      <div class="num">{o.totals.anchors.toLocaleString()}</div>
      <div class="delta">medium / high confidence</div>
    </div>
    <div class="kpi is-accent">
      <div class="label">Papers</div>
      <div class="num">{o.totals.papers.toLocaleString()}</div>
      <div class="delta">arXiv-discovered</div>
    </div>
    <div class="kpi">
      <div class="label">Topics</div>
      <div class="num">{o.totals.topics}</div>
      <div class="delta">currently tracked</div>
    </div>
    <div class="kpi">
      <div class="label">Days</div>
      <div class="num">{o.series_7d.length}</div>
      <div class="delta">trailing window</div>
    </div>
  </div>

  <div class="section-head">
    <div class="label">Trend</div>
    <div class="h">Papers Discovered · Past 7 Days</div>
    <div class="meta">accent = today</div>
  </div>
  <div class="px-7 pt-7 pb-9">
    <div class="bars">
      {#each o.series_7d as d, i}
        <div class="bar" style="height: {(d.papers / maxP) * 100}%; background: {i === o.series_7d.length - 1 ? 'var(--accent)' : 'var(--ink)'}">
          <span class="value">{d.papers}</span>
          <span class="label">{d.date.slice(5)}</span>
        </div>
      {/each}
    </div>
  </div>

  <div class="section-head">
    <div class="label">Trend</div>
    <div class="h">Researchers Discovered · Past 7 Days</div>
    <div class="meta">new identities</div>
  </div>
  <div class="px-7 pt-7 pb-9">
    <div class="bars">
      {#each o.series_7d as d, i}
        <div class="bar" style="height: {(d.researchers / maxR) * 100}%; background: {i === o.series_7d.length - 1 ? 'var(--accent)' : 'var(--ink)'}">
          <span class="value">{d.researchers}</span>
          <span class="label">{d.date.slice(5)}</span>
        </div>
      {/each}
    </div>
  </div>

  <div class="section-head">
    <div class="label">Roster</div>
    <div class="h">Top Collaborators</div>
    <div class="meta">most paper-authorships overall</div>
  </div>
  <table class="board-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Role</th>
        <th>Confidence</th>
        <th class="text-right">Papers</th>
      </tr>
    </thead>
    <tbody>
      {#each data.topCollab as r}
        <tr>
          <td>
            <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
            {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
          </td>
          <td class="font-mono text-xs uppercase tracking-wider text-n600">{roleLabel(r.current_role)}</td>
          <td>
            {#if r.confidence_level === 'high'}
              <span class="badge anchor">Anchor</span>
            {:else if r.confidence_level === 'medium'}
              <span class="badge">S2 verified</span>
            {:else}
              <span class="badge">Auto</span>
            {/if}
          </td>
          <td class="text-right font-mono">{r.n_papers}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  <div class="section-head">
    <div class="label">Distribution</div>
    <div class="h">By Topic</div>
    <div class="meta">papers per topic</div>
  </div>
  <table class="board-table">
    <thead>
      <tr>
        <th>Topic</th>
        <th>中文</th>
        <th class="text-right">Papers</th>
      </tr>
    </thead>
    <tbody>
      {#each data.byTopic as t}
        <tr>
          <td><a href={`/topics/${t.slug}`}>{t.name}</a></td>
          <td class="font-serif text-n600">{t.name_zh ?? '—'}</td>
          <td class="text-right font-mono">{t.n_papers}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
