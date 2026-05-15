<script lang="ts">
  import { t } from './i18n';
  import type { StoryItem } from './api';
  import { arxivUrl, blurb } from './api';

  let {
    leftItems = [],
    rightItems = [],
    rightAccent = false,
  }: { leftItems: StoryItem[]; rightItems: StoryItem[]; rightAccent?: boolean } = $props();
</script>

<section class="hero">
  <div class="hero-head">
    <div class="label">{$t('hero.label')}</div>
    <div class="h">{$t('hero.title')}</div>
    <div class="meta">{$t('hero.meta')}</div>
  </div>
  <div class="hero-cols">
    <div class="hero-col">
      <div class="col-label">
        <span>{$t('hero.leftLabel')}</span>
        <span class="col-meta">{$t('hero.leftMeta')}</span>
      </div>
      {#if leftItems.length === 0}
        <div class="hero-empty">{$t('hero.emptyLeft')}</div>
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
                  : ''} · {item.paper.n_authors} {$t('hero.rankAuthors')}
              </div>
            </div>
            <div class="right">
              <div class="v">{item.paper.n_authors}</div>
              <div class="l">{$t('hero.rankAuthorsLabel')}</div>
            </div>
          </div>
        {/each}
      {/if}
    </div>
    <div class="hero-col" class:is-accent={rightAccent}>
      <div class="col-label">
        <span>{$t('hero.rightLabel')}</span>
        <span class="col-meta">{$t('hero.rightMeta')}</span>
      </div>
      {#if rightItems.length === 0}
        <div class="hero-empty">{$t('hero.emptyRight')}</div>
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
