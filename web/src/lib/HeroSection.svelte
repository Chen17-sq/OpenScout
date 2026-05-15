<script lang="ts">
  import type { StoryItem } from './api';
  import { arxivUrl, blurb } from './api';

  let {
    leftLabel = 'Left',
    leftMeta = '',
    rightLabel = 'Right',
    rightMeta = '',
    leftItems = [],
    rightItems = [],
    rightAccent = false,
  }: {
    leftLabel: string;
    leftMeta?: string;
    rightLabel: string;
    rightMeta?: string;
    leftItems: StoryItem[];
    rightItems: StoryItem[];
    rightAccent?: boolean;
  } = $props();
</script>

<section class="hero">
  <div class="hero-head">
    <div class="label">FRONT PAGE</div>
    <div class="h">Today's Edition</div>
    <div class="meta">Top 6 each side · auto-ranked</div>
  </div>
  <div class="hero-cols">
    <div class="hero-col">
      <div class="col-label">
        <span>{leftLabel}</span>
        <span class="col-meta">{leftMeta}</span>
      </div>
      {#if leftItems.length === 0}
        <div class="hero-empty">今日无候选</div>
      {:else}
        {#each leftItems.slice(0, 6) as item, i}
          <div class="hero-story">
            <div class="rank">{String(i + 1).padStart(2, '0')}</div>
            <div class="body">
              <a href={`/researchers/${item.researcher.slug}`} class="title">{item.paper.title}</a>
              {#if item.paper.abstract}
                <div class="blurb">{blurb(item.paper.abstract, 130)}</div>
              {/if}
              <div class="smeta">
                {item.researcher.name_en}{item.researcher.name_zh
                  ? ` · ${item.researcher.name_zh}`
                  : ''} · {item.paper.n_authors} authors
              </div>
            </div>
            <div class="right">
              <div class="v">{item.paper.n_authors}</div>
              <div class="l">authors</div>
            </div>
          </div>
        {/each}
      {/if}
    </div>
    <div class="hero-col" class:is-accent={rightAccent}>
      <div class="col-label">
        <span>{rightLabel}</span>
        <span class="col-meta">{rightMeta}</span>
      </div>
      {#if rightItems.length === 0}
        <div class="hero-empty">今日无更新</div>
      {:else}
        {#each rightItems.slice(0, 6) as item, i}
          <div class="hero-story">
            <div class="rank">{String(i + 1).padStart(2, '0')}</div>
            <div class="body">
              <a href={`/researchers/${item.researcher.slug}`} class="title">{item.paper.title}</a>
              {#if item.paper.abstract}
                <div class="blurb">{blurb(item.paper.abstract, 130)}</div>
              {/if}
              <div class="smeta">
                {item.researcher.name_en}{item.researcher.name_zh
                  ? ` · ${item.researcher.name_zh}`
                  : ''} · {item.paper.topics.join(' / ') || 'arxiv'}
              </div>
            </div>
            <div class="right">
              <a class="v" href={arxivUrl(item.paper.arxiv_id)} target="_blank" rel="noreferrer"
                >arxiv</a
              >
              <div class="l">→</div>
            </div>
          </div>
        {/each}
      {/if}
    </div>
  </div>
</section>
