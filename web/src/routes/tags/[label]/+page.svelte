<script lang="ts">
  import { t } from '$lib/i18n';
  import { roleLabel } from '$lib/api';

  let { data } = $props();

  const detail = $derived(data.detail);
  const researchers = $derived(detail?.researchers ?? []);
  const type = $derived(detail?.type ?? 'topic');
  const count = $derived(detail?.count ?? researchers.length);

  const typeLabelKey = $derived(
    type === 'signal'
      ? 'tags.typeSignal'
      : type === 'institution'
        ? 'tags.typeInstitution'
        : 'tags.typeTopic',
  );

  const flag = (cc: string | null | undefined): string => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };

  const scoreFmt = (s: number | null | undefined): string =>
    s == null ? '—' : s.toFixed(2);
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('tags.label')}</div>
    <div class="h">
      {data.label}
      <span class="type-chip t-{type}">{$t(typeLabelKey)}</span>
    </div>
    <div class="meta">{$t('tags.countResearchers', { n: count.toLocaleString() })}</div>
  </div>

  {#if researchers.length === 0}
    <div class="empty">
      <p>{$t('tags.emptyTag')}</p>
      <a class="back-link" href="/tags">{$t('tags.backToTags')}</a>
    </div>
  {:else}
    <table class="board-table">
      <thead>
        <tr>
          <th class="text-right" style="width: 50px">{$t('tags.colRank')}</th>
          <th>{$t('tags.colName')}</th>
          <th>{$t('tags.colCountry')}</th>
          <th>{$t('tags.colRole')}</th>
          <th class="text-right">{$t('tags.colH')}</th>
          <th class="text-right">{$t('tags.colScore')}</th>
        </tr>
      </thead>
      <tbody>
        {#each researchers as r, i}
          <tr>
            <td class="text-right font-mono text-n500">{i + 1}</td>
            <td>
              <a href={`/researchers/${r.slug}`}>{r.name_en}</a>
              {#if r.name_zh}<span class="text-n500 font-serif"> · {r.name_zh}</span>{/if}
            </td>
            <td class="font-mono text-xs">
              {r.country ? `${flag(r.country)} ${r.country}` : '—'}
            </td>
            <td class="font-mono text-xs uppercase tracking-wider text-n600">
              {roleLabel(r.current_role ?? null) || '—'}
            </td>
            <td class="text-right font-mono">{r.h_index ?? '—'}</td>
            <td class="text-right font-mono score">{scoreFmt(r.investability_score_v2)}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <div class="footer-nav">
      <a class="back-link" href="/tags">{$t('tags.backToTags')}</a>
    </div>
  {/if}
</section>

<style>
  .section-head .h {
    display: flex;
    align-items: baseline;
    gap: 14px;
    flex-wrap: wrap;
  }
  .type-chip {
    display: inline-flex;
    align-items: center;
    border: 1px solid var(--ink);
    padding: 3px 9px;
    font-family: 'Inter', sans-serif;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .type-chip.t-signal {
    background: #fffaf0;
    border: 1px dashed #b8860b;
    color: #8a6300;
  }
  .type-chip.t-institution {
    background: var(--ink);
    color: var(--paper);
  }
  .type-chip.t-topic {
    background: var(--paper);
    color: var(--ink);
  }
  .empty {
    padding: 60px 28px;
    text-align: center;
    font-family: 'Lora', serif;
  }
  .empty p {
    font-style: italic;
    color: var(--n500);
    font-size: 15px;
    margin: 0 0 18px 0;
  }
  .back-link {
    display: inline-block;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink);
    text-decoration: none;
    padding: 6px 14px;
    border: 1px solid var(--ink);
  }
  .back-link:hover {
    background: var(--ink);
    color: var(--paper);
  }
  .footer-nav {
    padding: 20px 28px 30px;
    border-top: 1px solid var(--muted);
  }
  .score {
    font-weight: 700;
    color: var(--ink);
  }
</style>
