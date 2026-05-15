<script lang="ts">
  import { t } from '$lib/i18n';
  import { roleLabel } from '$lib/api';

  let { data } = $props();
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('nav.tags')}</div>
    <div class="h">{data.label}</div>
    <div class="meta">{data.researchers.length} researchers</div>
  </div>

  <table class="board-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Role</th>
        <th>Country</th>
        <th class="text-right">Citations</th>
        <th class="text-right">h</th>
      </tr>
    </thead>
    <tbody>
      {#each data.researchers as r}
        <tr>
          <td>
            <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
            {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
          </td>
          <td class="font-mono text-xs uppercase tracking-wider text-n600">{roleLabel(r.current_role)}</td>
          <td class="font-mono text-xs">{r.country ?? '—'}</td>
          <td class="text-right font-mono">{(r.citation_count ?? 0).toLocaleString()}</td>
          <td class="text-right font-mono">{r.h_index ?? '—'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>
