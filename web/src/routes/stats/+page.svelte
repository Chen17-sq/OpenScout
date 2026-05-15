<script lang="ts">
  import { t } from '$lib/i18n';
  import { roleLabel } from '$lib/api';

  let { data } = $props();
  const o = $derived(data.overview);
  const maxP = $derived(Math.max(1, ...(o?.series_7d.map((d) => d.papers) ?? [1])));
  const maxR = $derived(Math.max(1, ...(o?.series_7d.map((d) => d.researchers) ?? [1])));
</script>

{#if !o}
  <div class="story-card">
    <div></div>
    <div class="blurb">{$t('stats.unavailable')}</div>
    <div></div>
  </div>
{:else}
  <div class="kpi-row">
    <div class="kpi">
      <div class="label">{$t('kpi.researchers')}</div>
      <div class="num">{o.totals.researchers.toLocaleString()}</div>
      <div class="delta">all confidence</div>
    </div>
    <div class="kpi">
      <div class="label">{$t('kpi.anchors')}</div>
      <div class="num">{o.totals.anchors.toLocaleString()}</div>
      <div class="delta">{$t('kpi.anchorsDelta')}</div>
    </div>
    <div class="kpi is-accent">
      <div class="label">{$t('kpi.papers')}</div>
      <div class="num">{o.totals.papers.toLocaleString()}</div>
      <div class="delta">{$t('kpi.papersDelta')}</div>
    </div>
    <div class="kpi">
      <div class="label">{$t('kpi.topicsCount')}</div>
      <div class="num">{o.totals.topics}</div>
      <div class="delta">{$t('kpi.topicsDelta')}</div>
    </div>
    <div class="kpi">
      <div class="label">{$t('kpi.days')}</div>
      <div class="num">{o.series_7d.length}</div>
      <div class="delta">{$t('kpi.daysDelta')}</div>
    </div>
  </div>

  <div class="section-head">
    <div class="label">Trend</div>
    <div class="h">{$t('stats.papersTrend')}</div>
    <div class="meta">{$t('stats.papersTrendMeta')}</div>
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
    <div class="h">{$t('stats.researchersTrend')}</div>
    <div class="meta">{$t('stats.researchersTrendMeta')}</div>
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
    <div class="h">{$t('stats.topCollab')}</div>
    <div class="meta">{$t('stats.topCollabMeta')}</div>
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
              <span class="badge">OpenAlex</span>
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
    <div class="h">{$t('stats.byTopic')}</div>
    <div class="meta">{$t('stats.byTopicMeta')}</div>
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
      {#each data.byTopic as t_}
        <tr>
          <td><a href={`/topics/${t_.slug}`}>{t_.name}</a></td>
          <td class="font-serif text-n600">{t_.name_zh ?? '—'}</td>
          <td class="text-right font-mono">{t_.n_papers}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
