<script lang="ts">
  import { t, locale } from '$lib/i18n';

  let { data } = $props();

  const signals = $derived(data.overview.signal ?? []);
  const institutions = $derived(data.overview.institution ?? []);
  const allTopics = $derived(data.overview.topic ?? []);

  // Split topics: generic (level 0 — OpenAlex catch-alls like "Computer science")
  // is folded into a collapsible block so specific, level >= 2 topics dominate.
  const genericTopics = $derived(allTopics.filter((x) => (x.level ?? 0) === 0));
  const specificTopics = $derived(allTopics.filter((x) => (x.level ?? 0) !== 0));

  let showGeneric = $state(false);

  const isEmpty = $derived(
    signals.length === 0 && institutions.length === 0 && allTopics.length === 0,
  );

  const flag = (cc: string | null | undefined): string => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('tags.label')}</div>
    <div class="h">{$t('tags.title')}</div>
    <div class="meta">{$t('tags.meta')}</div>
  </div>

  {#if isEmpty}
    <div class="empty">
      {$t('tags.emptyOverview')}
    </div>
  {:else}
    <!-- Signals -->
    {#if signals.length > 0}
      <div class="tag-block">
        <div class="block-head">
          <h3>{$t('tags.signalsHeader')}</h3>
          <span class="block-meta">{$t('tags.signalsMeta')}</span>
          <span class="block-count">{signals.length}</span>
        </div>
        <div class="tag-list">
          {#each signals as tag}
            <a class="tag t-signal" href={`/tags/${encodeURIComponent(tag.label)}`}>
              {$locale === 'zh' && tag.label_zh ? tag.label_zh : tag.label}
              <span class="tag-count">{tag.count}</span>
            </a>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Institutions -->
    {#if institutions.length > 0}
      <div class="tag-block">
        <div class="block-head">
          <h3>{$t('tags.institutionsHeader')}</h3>
          <span class="block-meta">{$t('tags.institutionsMeta')}</span>
          <span class="block-count">{institutions.length}</span>
        </div>
        <div class="tag-list">
          {#each institutions as tag}
            <a class="tag t-institution" href={`/tags/${encodeURIComponent(tag.label)}`}>
              {tag.label}
              {#if tag.country}<span class="tag-meta">{flag(tag.country)}</span>{/if}
              <span class="tag-count">{tag.count}</span>
            </a>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Topics -->
    {#if allTopics.length > 0}
      <div class="tag-block">
        <div class="block-head">
          <h3>{$t('tags.topicsHeader')}</h3>
          <span class="block-meta">{$t('tags.topicsMeta')}</span>
          <span class="block-count">{specificTopics.length}</span>
        </div>
        <div class="tag-list">
          {#each specificTopics as tag}
            <a class="tag t-topic" href={`/tags/${encodeURIComponent(tag.label)}`}>
              {tag.label}
              <span class="tag-count">{tag.count}</span>
            </a>
          {/each}
        </div>

        {#if genericTopics.length > 0}
          <div class="generic-fold">
            <button
              type="button"
              class="fold-toggle"
              onclick={() => (showGeneric = !showGeneric)}
              aria-expanded={showGeneric}
            >
              {showGeneric
                ? $t('tags.hideGeneric')
                : $t('tags.showGeneric', { n: genericTopics.length })}
            </button>
            {#if showGeneric}
              <div class="tag-list generic">
                {#each genericTopics as tag}
                  <a class="tag t-topic t-generic" href={`/tags/${encodeURIComponent(tag.label)}`}>
                    {tag.label}
                    <span class="tag-count">{tag.count}</span>
                  </a>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</section>

<style>
  .empty {
    padding: 60px 28px;
    text-align: center;
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n500);
    font-size: 15px;
  }
  .tag-block {
    padding: 28px 28px 32px;
    border-bottom: 1px solid var(--muted);
  }
  .tag-block:last-child {
    border-bottom: none;
  }
  .block-head {
    display: flex;
    align-items: baseline;
    gap: 14px;
    margin-bottom: 18px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--muted);
  }
  .block-head h3 {
    font-family: 'Playfair Display', serif;
    font-weight: 800;
    font-size: 22px;
    letter-spacing: -0.5px;
    color: var(--ink);
    margin: 0;
  }
  .block-head .block-meta {
    font-family: 'Lora', serif;
    font-style: italic;
    font-size: 12.5px;
    color: var(--n500);
    flex: 1;
  }
  .block-head .block-count {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--n500);
  }

  /* Chip styling mirrors `.tag` classes from researchers/[slug] */
  .tag-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .tag-list.generic {
    margin-top: 12px;
  }
  .tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--ink);
    padding: 5px 11px;
    font-family: 'Inter', sans-serif;
    font-size: 11.5px;
    font-weight: 600;
    color: var(--ink);
    text-decoration: none;
    transition:
      background 0.12s,
      color 0.12s;
  }
  .tag:hover {
    background: var(--ink);
    color: var(--paper);
  }
  .tag-count {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 500;
    color: var(--n500);
  }
  .tag:hover .tag-count {
    color: var(--paper);
    opacity: 0.7;
  }
  .tag-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    opacity: 0.85;
  }
  /* Signal: amber chip */
  .tag.t-signal {
    background: #fffaf0;
    border: 1px dashed #b8860b;
    color: #8a6300;
  }
  .tag.t-signal:hover {
    background: #b8860b;
    color: var(--paper);
  }
  .tag.t-signal .tag-count {
    color: #8a6300;
    opacity: 0.7;
  }
  /* Institution: solid ink chip */
  .tag.t-institution {
    background: var(--ink);
    color: var(--paper);
    border-color: var(--ink);
  }
  .tag.t-institution:hover {
    background: var(--accent);
    border-color: var(--accent);
  }
  .tag.t-institution .tag-count {
    color: var(--paper);
    opacity: 0.7;
  }
  /* Generic topic tags (level=0): faded */
  .tag.t-topic.t-generic {
    border-color: var(--n400);
    color: var(--n500);
  }
  .tag.t-topic.t-generic .tag-count {
    color: var(--n400);
  }

  .generic-fold {
    margin-top: 16px;
  }
  .fold-toggle {
    background: transparent;
    border: 1px solid var(--n400);
    color: var(--n600);
    padding: 5px 12px;
    font-family: 'Inter', sans-serif;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    cursor: pointer;
  }
  .fold-toggle:hover {
    background: var(--n100);
    color: var(--ink);
    border-color: var(--ink);
  }
</style>
