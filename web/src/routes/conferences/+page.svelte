<script lang="ts">
  import { t } from '$lib/i18n';
  let { data } = $props();

  // Group venues by conference prefix
  const groups = $derived.by(() => {
    const out: Record<string, Array<{ venue: string; n_papers: number }>> = {};
    for (const v of data.venues) {
      const head = v.venue.split(/\s+/)[0];
      if (!out[head]) out[head] = [];
      out[head].push(v);
    }
    return Object.entries(out).sort((a, b) => {
      const an = a[1].reduce((s, x) => s + x.n_papers, 0);
      const bn = b[1].reduce((s, x) => s + x.n_papers, 0);
      return bn - an;
    });
  });

  const totalPapers = $derived(data.venues.reduce((s, v) => s + v.n_papers, 0));
</script>

<section>
  <div class="section-head">
    <div class="label">Index</div>
    <div class="h">Conferences</div>
    <div class="meta">{data.venues.length} venues · {totalPapers.toLocaleString()} papers</div>
  </div>

  {#each groups as [conf, venues]}
    <article class="conf-group">
      <h3 class="conf-name">{conf}</h3>
      <ul>
        {#each venues as v}
          {@const tier = v.venue.toLowerCase().includes('oral') || v.venue.toLowerCase().includes('spotlight') || v.venue.toLowerCase().includes('best') ? 'tier' : ''}
          <li class:tier>
            <a href={`/conferences/${encodeURIComponent(v.venue)}`}>{v.venue}</a>
            <span class="n">{v.n_papers}</span>
          </li>
        {/each}
      </ul>
    </article>
  {/each}
</section>

<style>
  .conf-group {
    padding: 22px 28px;
    border-bottom: 1px solid var(--muted);
  }
  .conf-name {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 28px;
    margin: 0 0 14px;
    letter-spacing: -0.5px;
  }
  .conf-group ul {
    list-style: none;
    padding: 0;
    margin: 0;
    columns: 2;
    column-gap: 24px;
  }
  .conf-group li {
    font-family: 'Lora', serif;
    font-size: 14px;
    line-height: 1.7;
    break-inside: avoid;
  }
  .conf-group li.tier a {
    color: var(--accent);
    font-weight: 700;
  }
  .conf-group li a {
    color: var(--ink);
    text-decoration: none;
  }
  .conf-group li a:hover {
    color: var(--accent);
  }
  .conf-group li .n {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n500);
    margin-left: 8px;
  }
</style>
