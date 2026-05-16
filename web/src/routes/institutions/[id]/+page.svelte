<script lang="ts">
  import { roleLabel } from '$lib/api';

  let { data } = $props();
  const inst = $derived(data.inst);

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };
</script>

<section>
  <div class="section-head">
    <div class="label">Institution</div>
    <div class="h">{inst.name}</div>
    <div class="meta">
      {inst.name_zh ?? ''}
      {#if inst.country}· {flag(inst.country)} {inst.country}{/if}
      {#if inst.type}· {inst.type.toUpperCase()}{/if}
    </div>
  </div>

  <div class="section-head">
    <div class="label">Roster</div>
    <div class="h">Researchers</div>
    <div class="meta">{inst.researchers.length}</div>
  </div>

  <table class="board-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Role</th>
        <th>Tags</th>
        <th class="text-right">h</th>
        <th class="text-right">Cites</th>
      </tr>
    </thead>
    <tbody>
      {#each inst.researchers as r}
        <tr>
          <td>
            <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
            {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
          </td>
          <td class="font-mono text-xs uppercase tracking-wider text-n600">{roleLabel(r.current_role)}</td>
          <td>
            {#each r.tags ?? [] as tag}<span class="badge">{tag.label}</span>{/each}
          </td>
          <td class="text-right font-mono">{r.h_index ?? '—'}</td>
          <td class="text-right font-mono">{(r.citation_count ?? 0).toLocaleString()}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>
