<script lang="ts">
  let { data } = $props();
</script>

<section>
  <div class="section-head">
    <div class="label">Topics</div>
    <div class="h">By Area</div>
    <div class="meta">{data.topics.length} topics tracked</div>
  </div>

  {#each data.topics as t}
    <article class="story-card">
      <div class="no">{t.n_papers}</div>
      <div>
        <a class="title" href={`/topics/${t.slug}`}>{t.name}</a>
        {#if t.name_zh}<div class="by">{t.name_zh}</div>{/if}
        {#if t.description}<div class="blurb">{t.description}</div>{/if}
      </div>
      <div class="right">
        <span class="v">{t.n_papers}</span>
        <div>papers</div>
      </div>
    </article>
  {/each}
</section>
