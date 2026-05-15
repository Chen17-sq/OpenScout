<script lang="ts">
  import type { StoryItem } from './api';
  import { arxivUrl, blurb, roleLabel } from './api';

  let {
    label,
    title,
    meta = '',
    items,
    emptyMessage = '_今日无候选_',
  }: {
    label: string;
    title: string;
    meta?: string;
    items: StoryItem[];
    emptyMessage?: string;
  } = $props();
</script>

<section>
  <div class="section-head">
    <div class="label">{label}</div>
    <div class="h">{title}</div>
    <div class="meta">{meta || `${items.length} item${items.length === 1 ? '' : 's'}`}</div>
  </div>

  {#if items.length === 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">{emptyMessage}</div>
      <div></div>
    </div>
  {:else}
    {#each items as item, i}
      <article class="story-card">
        <div class="no">{String(i + 1).padStart(2, '0')}</div>
        <div>
          <a href={arxivUrl(item.paper.arxiv_id)} target="_blank" rel="noreferrer" class="title">
            {item.paper.title}
          </a>
          <div class="by">
            <a href={`/researchers/${item.researcher.slug}`} class="name">
              {item.researcher.name_en}{item.researcher.name_zh ? ` · ${item.researcher.name_zh}` : ''}
            </a>
            {#if item.researcher.current_role}
              · {roleLabel(item.researcher.current_role)}
            {/if}
            · 第 1 作者 · {item.paper.n_authors} 人合作
          </div>
          {#if item.paper.one_liner_zh}
            <div class="blurb">{item.paper.one_liner_zh}</div>
          {:else if item.paper.abstract}
            <div class="blurb">{blurb(item.paper.abstract, 250)}</div>
          {/if}
          {#if item.reasoning}
            <div class="reason">▸ 选中原因：{item.reasoning}</div>
          {/if}
        </div>
        <div class="right">
          <span class="v">{item.paper.n_authors}</span>
          <div>合作</div>
          {#each item.paper.topics as t}
            <div class="topic">{t}</div>
          {/each}
        </div>
      </article>
    {/each}
  {/if}
</section>
