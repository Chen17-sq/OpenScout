<script lang="ts">
  import { t } from '$lib/i18n';
  let { data } = $props();
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('archive.label')}</div>
    <div class="h">{$t('archive.title')}</div>
    <div class="meta">{$t('archive.meta', { n: data.briefs.length })}</div>
  </div>

  {#if data.briefs.length === 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">{$t('archive.empty')}</div>
      <div></div>
    </div>
  {:else}
    <table class="board-table">
      <thead>
        <tr>
          <th>{$t('archive.colIssue')}</th>
          <th>{$t('archive.colDate')}</th>
          <th>{$t('archive.colGenerated')}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each data.briefs as b}
          <tr>
            <td class="font-mono">VOL. {b.volume} · NO. {String(b.issue).padStart(3, '0')}</td>
            <td class="font-display text-lg">{b.brief_date}</td>
            <td class="font-mono text-xs text-n500">{b.generated_at?.slice(0, 19) ?? '—'}</td>
            <td><a href={`/daily/${b.brief_date}`}>{$t('archive.read')}</a></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>
