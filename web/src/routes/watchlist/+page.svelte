<script lang="ts">
  import { onMount } from 'svelte';
  import { watchlist } from '$lib/watchlist';
  import { apiFetch } from '$lib/api';
  import { t } from '$lib/i18n';
  import { roleLabel } from '$lib/api';

  type R = {
    slug: string;
    name_en: string;
    name_zh: string | null;
    current_role: string | null;
    country: string | null;
    confidence_level: string;
    h_index: number | null;
    citation_count: number | null;
    tags: Array<{ label: string }>;
  };

  let researchers = $state<R[]>([]);
  let loading = $state(true);

  $effect(() => {
    const slugs = $watchlist;
    loading = true;
    Promise.all(
      slugs.map((slug) => apiFetch<R>(`/researchers/${slug}`)),
    ).then((rs) => {
      researchers = rs.filter((x): x is R => !!x);
      loading = false;
    });
  });
</script>

<section>
  <div class="section-head">
    <div class="label">Watchlist</div>
    <div class="h">★ Starred Researchers</div>
    <div class="meta">{$watchlist.length} starred · saved locally only</div>
  </div>

  {#if loading}
    <div class="story-card">
      <div></div>
      <div class="blurb">Loading…</div>
      <div></div>
    </div>
  {:else if researchers.length === 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">
        Watchlist 是空的。在任意研究者详情页点击 ★ 收藏，会保存在浏览器本地。
      </div>
      <div></div>
    </div>
  {:else}
    <table class="board-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Role</th>
          <th>Country</th>
          <th>Tags</th>
          <th class="text-right">Cites</th>
          <th class="text-right">h</th>
        </tr>
      </thead>
      <tbody>
        {#each researchers as r}
          <tr>
            <td>
              <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
              {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
            </td>
            <td class="font-mono text-xs">{roleLabel(r.current_role)}</td>
            <td class="font-mono text-xs">{r.country ?? '—'}</td>
            <td>
              {#each r.tags?.slice(0, 3) ?? [] as tag}
                <span class="badge">{tag.label}</span>
              {/each}
            </td>
            <td class="text-right font-mono">{(r.citation_count ?? 0).toLocaleString()}</td>
            <td class="text-right font-mono">{r.h_index ?? '—'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>
