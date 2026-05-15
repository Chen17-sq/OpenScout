<script lang="ts">
  import { t } from '$lib/i18n';

  let { data } = $props();

  // Min/max for font-size scaling
  const maxCount = $derived(Math.max(1, ...data.tags.map((x) => x.count)));
  const minCount = $derived(Math.min(...data.tags.map((x) => x.count)));

  const fontSize = (count: number): number => {
    const range = Math.max(1, maxCount - minCount);
    const norm = (count - minCount) / range;
    // 13px → 38px
    return Math.round(13 + norm * 25);
  };
</script>

<section>
  <div class="section-head">
    <div class="label">Index</div>
    <div class="h">{$t('nav.tags')}</div>
    <div class="meta">{data.tags.length} distinct · size by count</div>
  </div>

  {#if data.tags.length === 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">No tags aggregated yet. Run <code>openscout enrich-openalex</code>.</div>
      <div></div>
    </div>
  {:else}
    <div class="cloud">
      {#each data.tags as tag}
        <a
          href={`/tags/${encodeURIComponent(tag.label)}`}
          class="cloud-tag"
          style="font-size: {fontSize(tag.count)}px"
          title="{tag.count} researchers · avg score {tag.avg_score.toFixed(2)}"
        >{tag.label}<sup>{tag.count}</sup></a>
      {/each}
    </div>
  {/if}
</section>

<style>
  .cloud {
    padding: 36px 28px 60px;
    display: flex;
    flex-wrap: wrap;
    gap: 14px 22px;
    align-items: baseline;
    line-height: 1.6;
  }
  .cloud-tag {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    color: var(--ink);
    text-decoration: none;
    transition: color 0.12s;
  }
  .cloud-tag:hover {
    color: var(--accent);
  }
  .cloud-tag sup {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 500;
    color: var(--n500);
    margin-left: 4px;
  }
</style>
