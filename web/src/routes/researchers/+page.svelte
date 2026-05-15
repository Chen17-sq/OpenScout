<script lang="ts">
  import { roleLabel } from '$lib/api';

  let { data } = $props();
  const list = $derived(data.data?.items ?? []);
  const total = $derived(data.data?.total ?? 0);
</script>

<section>
  <div class="section-head">
    <div class="label">Roster</div>
    <div class="h">All Researchers</div>
    <div class="meta">{total.toLocaleString()} tracked · filter via querystring</div>
  </div>

  <div class="px-7 pt-4 pb-2 font-mono text-[11px] uppercase text-n600 tracking-wider">
    <a href="/researchers" class:underline={!data.filters.confidence && !data.filters.stage}>All</a>
    {' · '}
    <a href="/researchers?confidence=high" class:underline={data.filters.confidence === 'high'}>High confidence (anchors)</a>
    {' · '}
    <a href="/researchers?confidence=low" class:underline={data.filters.confidence === 'low'}>Low (auto-discovered)</a>
    {' · '}
    <a href="/researchers?topic=embodied" class:underline={data.filters.topic === 'embodied'}>具身</a>
    {' · '}
    <a href="/researchers?topic=world_models" class:underline={data.filters.topic === 'world_models'}>世界模型</a>
    {' · '}
    <a href="/researchers?topic=ai4sci" class:underline={data.filters.topic === 'ai4sci'}>AI4Sci</a>
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
      {#each list as r}
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
              <span class="badge" style="color:#737373;border-color:#a3a3a3">Auto</span>
            {/if}
          </td>
          <td class="text-right font-mono">{r.n_papers}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>
