<script lang="ts">
  import { t } from '$lib/i18n';
  let { data } = $props();
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('topics.sectionLabel')}</div>
    <div class="h">{$t('topics.listTitle')}</div>
    <div class="meta">{$t('topics.listMeta', { n: data.topics.length })}</div>
  </div>

  {#each data.topics as t_}
    <article class="story-card">
      <div class="no">{t_.n_papers}</div>
      <div>
        <a class="title" href={`/topics/${t_.slug}`}>{t_.name}</a>
        {#if t_.name_zh}<div class="by">{t_.name_zh}</div>{/if}
        {#if t_.description}<div class="blurb">{t_.description}</div>{/if}
      </div>
      <div class="right">
        <span class="v">{t_.n_papers}</span>
        <div>{$t('topics.nPapers')}</div>
      </div>
    </article>
  {/each}
</section>
