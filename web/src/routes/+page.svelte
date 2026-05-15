<script lang="ts">
  import { marked } from 'marked';

  let { data } = $props();

  const html = $derived(data.brief ? marked.parse(data.brief.rendered_md) : '');
</script>

{#if data.error}
  <header class="rule-bottom pb-4 mb-10">
    <p class="font-mono text-[11px] tracking-[0.2em] uppercase">
      VOL. 1 · NO. 001 &nbsp;·&nbsp; BEIJING EDITION
    </p>
    <h1 class="masthead text-6xl md:text-7xl font-bold mt-2">OpenScout</h1>
    <p class="mt-2 italic text-base">All The Researchers Fit To Watch.</p>
  </header>

  <section class="bg-red-50 border border-red-200 rounded p-4 text-sm">
    <p class="font-semibold">Backend offline</p>
    <p class="text-stone-700">{data.error}</p>
  </section>
{:else if data.brief}
  <article class="prose prose-stone max-w-none prose-headings:masthead prose-pre:bg-stone-100 prose-pre:text-stone-800 prose-table:text-sm">
    {@html html}
  </article>

  <footer class="mt-16 pt-6 rule-top text-xs text-stone-500 font-mono">
    Vol. {data.brief.volume} · No. {String(data.brief.issue).padStart(3, '0')} · generated {data.brief.generated_at}
  </footer>
{/if}
