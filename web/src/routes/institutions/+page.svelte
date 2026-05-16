<script lang="ts">
  import { t } from '$lib/i18n';
  let { data } = $props();

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };
</script>

<section>
  <div class="section-head">
    <div class="label">Index</div>
    <div class="h">Institutions</div>
    <div class="meta">{data.items.length} tracked</div>
  </div>

  <table class="board-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Country</th>
        <th>Type</th>
        <th class="text-right">Researchers</th>
        <th class="text-right">Total citations</th>
      </tr>
    </thead>
    <tbody>
      {#each data.items as inst}
        <tr>
          <td>
            <a href={`/institutions/${inst.id}`}>{inst.name}</a>
            {#if inst.name_zh}<span class="text-n500 font-serif"> · {inst.name_zh}</span>{/if}
          </td>
          <td class="font-mono text-xs">{inst.country ? `${flag(inst.country)} ${inst.country}` : '—'}</td>
          <td class="font-mono text-xs uppercase tracking-wider text-n600">{inst.type ?? '—'}</td>
          <td class="text-right font-mono">{inst.n_researchers}</td>
          <td class="text-right font-mono">{inst.total_citations.toLocaleString()}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>
