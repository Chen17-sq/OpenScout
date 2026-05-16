<script lang="ts">
  import { arxivUrl, blurb } from '$lib/api';

  let { data } = $props();
  const brief = $derived(data.brief);
</script>

{#if brief}
  <article class="print-paper">
    <header>
      <p class="strip">VOL. 1 · NO. {String(brief.issue).padStart(3, '0')} · {brief.brief_date}</p>
      <h1 class="nameplate-print">OpenScout</h1>
      <p class="tag-print"><em>All The Researchers Fit To Watch.</em></p>
    </header>

    <table class="kpi-print">
      <tbody>
        <tr>
          <td><div class="num">{brief.kpi.tracked.toLocaleString()}</div><div>tracked</div></td>
          <td><div class="num accent">{brief.kpi.today_papers}</div><div>today papers</div></td>
          <td><div class="num accent">{brief.kpi.today_emergences}</div><div>new faces</div></td>
          <td><div class="num">{brief.kpi.soon_graduating}</div><div>grad PhD</div></td>
          <td><div class="num">{brief.kpi.incoming_ap}</div><div>incoming AP</div></td>
        </tr>
      </tbody>
    </table>

    {#each [
      { title: '今日新冒头 New First-Authors', items: brief.new_first_authors },
      { title: '动态更新 Anchor Activity', items: brief.anchor_activity },
      { title: '即将毕业 Graduating PhDs', items: brief.soon_graduating_picks },
      { title: '即将入职 AP', items: brief.incoming_ap_picks },
      { title: '热门工作 Hot Papers', items: brief.hot_papers },
      { title: 'Sleeper Picks', items: brief.sleeper_picks },
    ] as section}
      {#if section.items.length}
        <h2 class="section-print">{section.title}</h2>
        {#each section.items as item, i}
          <div class="item-print">
            <span class="rank">{String(i + 1).padStart(2, '0')}</span>
            <strong>{item.paper.title}</strong>
            <em>{item.researcher.name_en}{item.researcher.name_zh ? ` · ${item.researcher.name_zh}` : ''}</em>
            {#if item.paper.abstract}<p>{blurb(item.paper.abstract, 240)}</p>{/if}
            {#if item.reasoning}<p class="reason">▸ {item.reasoning}</p>{/if}
            <span class="meta">arxiv:{item.paper.arxiv_id ?? '—'} · {item.paper.n_authors} authors</span>
          </div>
        {/each}
      {/if}
    {/each}

    <footer>
      <p>Printed from openscout.app · {brief.brief_date} · Use your browser's Save as PDF to archive.</p>
    </footer>
  </article>
{/if}

<style>
  :global(body) {
    background: white;
  }
  :global(.wrap > nav),
  :global(.wrap > .nav-shell),
  :global(.site-footer) {
    display: none;
  }
  :global(.wrap) {
    border: none;
    max-width: none;
    background: white;
    margin: 0;
  }
  .print-paper {
    max-width: 720px;
    margin: 40px auto;
    padding: 40px;
    background: white;
    color: black;
    font-family: 'Lora', Georgia, serif;
    font-size: 12px;
    line-height: 1.45;
  }
  header {
    text-align: center;
    border-bottom: 3px solid black;
    padding-bottom: 24px;
    margin-bottom: 24px;
  }
  .strip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin: 0 0 6px;
  }
  .nameplate-print {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 72px;
    margin: 0;
    letter-spacing: -2px;
  }
  .tag-print {
    margin: 8px 0 0;
    font-style: italic;
    font-size: 14px;
  }
  .kpi-print {
    width: 100%;
    border-collapse: collapse;
    margin: 0 0 24px;
    border-bottom: 2px solid black;
  }
  .kpi-print td {
    text-align: center;
    border-right: 1px solid #aaa;
    padding: 10px 8px;
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.15em;
  }
  .kpi-print td:last-child {
    border-right: none;
  }
  .kpi-print .num {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 28px;
    line-height: 1;
    margin-bottom: 4px;
    color: black;
  }
  .kpi-print .num.accent {
    color: #cc0000;
  }
  .section-print {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 22px;
    margin: 22px 0 12px;
    padding-bottom: 4px;
    border-bottom: 1px solid black;
  }
  .item-print {
    padding: 8px 0;
    border-bottom: 1px solid #ddd;
  }
  .item-print .rank {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 16px;
    color: #888;
    margin-right: 6px;
  }
  .item-print strong {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 13px;
  }
  .item-print em {
    display: block;
    font-style: normal;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    color: #555;
    margin-top: 2px;
  }
  .item-print p {
    margin: 4px 0;
    font-style: italic;
    color: #444;
  }
  .item-print p.reason {
    color: #cc0000;
    font-style: normal;
    font-weight: 600;
  }
  .item-print .meta {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    color: #888;
    margin-top: 4px;
  }
  footer {
    margin-top: 40px;
    border-top: 2px solid black;
    padding-top: 12px;
    text-align: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    color: #555;
  }
  @media print {
    .print-paper {
      margin: 0;
      padding: 20px;
    }
    @page {
      size: A4;
      margin: 1.4cm;
    }
  }
</style>
