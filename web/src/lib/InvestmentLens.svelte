<script lang="ts">
  // "Investment Lens · Today's Picks" — surfaces the top researchers by the
  // three-pillar work_score model. Each pick exposes WHY it ranked (which
  // pillars fired + raw reason tokens captured at scoring time), so the
  // investor can audit and trust the ranking — same audit philosophy as the
  // v1.3 provenance badges.

  import type { InvestmentPicks, InvestmentPick } from '$lib/api';
  import { arxivUrl, roleLabel } from '$lib/api';
  import { t } from '$lib/i18n';

  let { investment }: { investment: InvestmentPicks | null } = $props();

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };

  // Pillar bar colour by which signal is strongest — purely visual ranking aid.
  const pillarClass = (pick: InvestmentPick) => {
    if (!pick.top_paper) return 'pillar-buzz';
    const { breakthrough, commercial, buzz } = pick.top_paper;
    const max = Math.max(breakthrough, commercial, buzz);
    if (max === breakthrough) return 'pillar-breakthrough';
    if (max === commercial) return 'pillar-commercial';
    return 'pillar-buzz';
  };

  const positionLabel = (pos: number | null) => {
    if (!pos) return '';
    if (pos === 1) return $t('investment.posFirst');
    return `#${pos}`;
  };
</script>

{#if investment && investment.picks.length}
  <section class="lens">
    <header>
      <div class="label">Investment Lens</div>
      <div class="h">{$t('investment.title')}</div>
      <div class="meta">{$t('investment.meta')} · {investment.window_days}d window</div>
    </header>

    <div class="picks">
      {#each investment.picks as p, i}
        <article class="pick {pillarClass(p)}">
          <div class="num">{String(i + 1).padStart(2, '0')}</div>
          <div class="body">
            <div class="row1">
              <a class="name" href={`/researchers/${p.slug}`}>{p.name_en}</a>
              {#if p.name_zh}<span class="zh">{p.name_zh}</span>{/if}
              {#if p.country}<span class="flag">{flag(p.country)}</span>{/if}
              {#if p.current_role}<span class="role">{roleLabel(p.current_role)}</span>{/if}
              <span class="score">{p.score.toFixed(2)}</span>
            </div>

            {#if p.top_paper}
              <div class="paper">
                {#if p.top_paper.position}
                  <span class="pos">{positionLabel(p.top_paper.position)}</span>
                {/if}
                <a class="title" href={arxivUrl(p.top_paper.arxiv_id)} target="_blank" rel="noreferrer">
                  {p.top_paper.title}
                </a>
              </div>

              <div class="pillars">
                <div class="pillar">
                  <span class="pl">B</span>
                  <span class="bar"><span class="fill b" style="width: {p.top_paper.breakthrough * 100}%"></span></span>
                  <span class="v">{p.top_paper.breakthrough.toFixed(2)}</span>
                </div>
                <div class="pillar">
                  <span class="pl">C</span>
                  <span class="bar"><span class="fill c" style="width: {p.top_paper.commercial * 100}%"></span></span>
                  <span class="v">{p.top_paper.commercial.toFixed(2)}</span>
                </div>
                <div class="pillar">
                  <span class="pl">Z</span>
                  <span class="bar"><span class="fill z" style="width: {p.top_paper.buzz * 100}%"></span></span>
                  <span class="v">{p.top_paper.buzz.toFixed(2)}</span>
                </div>
              </div>

              {#if p.top_paper.reasons.length}
                <div class="why">
                  <span class="why-lbl">WHY</span>
                  {#each p.top_paper.reasons as r}
                    <span class="why-chip">{r}</span>
                  {/each}
                </div>
              {/if}
            {/if}
          </div>
        </article>
      {/each}
    </div>

    <footer class="legend">
      <span><strong>B</strong> {$t('investment.legendB')}</span>
      <span><strong>C</strong> {$t('investment.legendC')}</span>
      <span><strong>Z</strong> {$t('investment.legendZ')}</span>
    </footer>
  </section>
{/if}

<style>
  .lens {
    border-top: 4px double var(--ink);
    border-bottom: 1px solid var(--ink);
    background: var(--paper);
  }
  .lens header {
    padding: 22px 28px 14px;
    border-bottom: 1px solid var(--ink);
    display: grid;
    grid-template-columns: 150px 1fr auto;
    align-items: baseline;
    gap: 18px;
  }
  .label {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    color: var(--accent);
  }
  .h {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 32px;
    line-height: 1.05;
    color: var(--ink);
  }
  .meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n500);
    text-align: right;
  }
  .picks {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .pick {
    display: grid;
    grid-template-columns: 38px 1fr;
    padding: 16px 22px;
    border-right: 1px solid var(--muted);
    border-bottom: 1px solid var(--muted);
    gap: 12px;
  }
  .pick:nth-child(2n) {
    border-right: none;
  }
  .num {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 22px;
    color: var(--ink);
    line-height: 1;
  }
  .body {
    min-width: 0;
  }
  .row1 {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 6px;
  }
  .name {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 17px;
    color: var(--ink);
    text-decoration: none;
  }
  .name:hover {
    color: var(--accent);
  }
  .zh {
    font-family: 'Lora', serif;
    font-size: 13px;
    color: var(--n600);
  }
  .flag {
    font-size: 13px;
  }
  .role {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    font-weight: 700;
    text-transform: uppercase;
    border: 1px solid var(--ink);
    padding: 0 5px;
    color: var(--ink);
  }
  .score {
    margin-left: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 700;
    color: var(--accent);
  }
  .paper {
    font-family: 'Lora', serif;
    font-size: 13px;
    line-height: 1.4;
    color: var(--n700);
    margin-bottom: 8px;
  }
  .paper .pos {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    background: var(--ink);
    color: var(--paper);
    padding: 1px 4px;
    margin-right: 6px;
    vertical-align: 2px;
  }
  .paper .title {
    color: var(--ink);
    text-decoration: underline;
    text-decoration-color: var(--n400);
  }
  .paper .title:hover {
    color: var(--accent);
  }
  .pillars {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin: 8px 0 6px;
  }
  .pillar {
    display: grid;
    grid-template-columns: 14px 1fr 30px;
    align-items: center;
    gap: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
  }
  .pl {
    font-weight: 800;
    color: var(--n600);
  }
  .bar {
    height: 6px;
    background: var(--muted);
    display: block;
    position: relative;
  }
  .fill {
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
  }
  .fill.b {
    background: #6b3f9c; /* purple — breakthrough */
  }
  .fill.c {
    background: #2f7a3a; /* green — commercial */
  }
  .fill.z {
    background: var(--accent); /* accent — buzz */
  }
  .v {
    text-align: right;
    color: var(--n600);
  }
  .why {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 6px;
    align-items: center;
  }
  .why-lbl {
    font-family: 'Inter', sans-serif;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.16em;
    color: var(--n500);
  }
  .why-chip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    border: 1px solid var(--n400);
    padding: 1px 5px;
    color: var(--n700);
    background: var(--paper);
  }
  .legend {
    display: flex;
    gap: 22px;
    padding: 10px 28px;
    border-top: 1px solid var(--muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    color: var(--n600);
    background: var(--n100);
  }
  .legend strong {
    color: var(--ink);
    margin-right: 4px;
  }
  /* responsive: stack on narrow */
  @media (max-width: 760px) {
    .picks {
      grid-template-columns: 1fr;
    }
    .pick {
      border-right: none;
    }
    .lens header {
      grid-template-columns: 1fr;
    }
    .meta {
      text-align: left;
    }
  }
</style>
