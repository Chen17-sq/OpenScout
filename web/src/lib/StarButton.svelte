<script lang="ts">
  import { watchlist, toggle } from './watchlist';

  let { slug }: { slug: string } = $props();
  const starred = $derived($watchlist.includes(slug));
</script>

<button
  type="button"
  class="star"
  class:on={starred}
  onclick={(e) => {
    e.preventDefault();
    e.stopPropagation();
    toggle(slug);
  }}
  aria-pressed={starred}
  aria-label={starred ? '取消收藏' : '收藏'}
  title={starred ? 'Starred — click to remove' : 'Add to watchlist'}
>★</button>

<style>
  .star {
    background: transparent;
    border: 1px solid var(--n400);
    color: var(--n400);
    font-size: 14px;
    padding: 2px 8px;
    cursor: pointer;
    line-height: 1;
    font-family: 'Inter', sans-serif;
  }
  .star.on {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--paper);
  }
  .star:hover {
    border-color: var(--ink);
    color: var(--ink);
  }
  .star.on:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
