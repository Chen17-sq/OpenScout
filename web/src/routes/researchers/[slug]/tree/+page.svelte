<script lang="ts">
  import { t } from '$lib/i18n';
  import { roleLabel } from '$lib/api';

  let { data } = $props();
  const r = $derived(data.researcher);
  const advisorList = $derived(r.advisor ? [r.advisor] : r.inferred_advisors ?? []);
</script>

<section>
  <div class="section-head">
    <div class="label">Lineage</div>
    <div class="h">{r.name_en}{r.name_zh ? ` · ${r.name_zh}` : ''}</div>
    <div class="meta">academic tree</div>
  </div>

  <div class="tree">
    {#if advisorList.length}
      <div class="tree-row">
        <div class="tree-label">{$t('researcher.advisor')}</div>
        <div class="tree-cards">
          {#each advisorList as a}
            <a class="tree-card up" href={`/researchers/${a.slug}`}>
              <div class="t-name">{a.name_en}</div>
              {#if a.name_zh}<div class="t-zh">{a.name_zh}</div>{/if}
              {#if 'confidence' in a && a.confidence}
                <div class="t-conf">{a.confidence} confidence</div>
              {/if}
            </a>
          {/each}
        </div>
      </div>
      <div class="tree-conn">│</div>
    {/if}

    <div class="tree-row self">
      <div class="tree-label">{$t('researcher.sectionLabel')}</div>
      <div class="tree-card current">
        <div class="t-name">{r.name_en}</div>
        {#if r.name_zh}<div class="t-zh">{r.name_zh}</div>{/if}
        <div class="t-stats">
          h={r.h_index ?? '—'} · {r.citation_count?.toLocaleString() ?? '—'} cites · {roleLabel(r.current_role)}
        </div>
      </div>
    </div>

    {#if r.students.length}
      <div class="tree-conn">│</div>
      <div class="tree-row">
        <div class="tree-label">{$t('researcher.students')}</div>
        <div class="tree-cards">
          {#each r.students as s}
            <a class="tree-card down" href={`/researchers/${s.slug}`}>
              <div class="t-name">{s.name_en}</div>
              {#if s.name_zh}<div class="t-zh">{s.name_zh}</div>{/if}
              <div class="t-stats">h={s.h_index ?? '—'} · {roleLabel(s.current_role)}</div>
            </a>
          {/each}
        </div>
      </div>
    {/if}

    {#if !advisorList.length && !r.students.length}
      <p class="tree-empty">
        无 lineage 数据。<br />
        Lineage 通过两种方式构建：(1) 在 seeds/researchers.yaml 标 advisor_id；
        (2) <code>openscout backfill-works</code> 抓完 anchors 的全部 papers
        后跑 <code>openscout lineage</code> 触发师承推断。
      </p>
    {/if}
  </div>
</section>

<style>
  .tree {
    padding: 60px 28px 80px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
  }
  .tree-row {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    padding: 14px 0;
  }
  .tree-label {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.22em;
    color: var(--n500);
  }
  .tree-cards {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    justify-content: center;
  }
  .tree-card {
    display: inline-block;
    padding: 14px 22px;
    border: 1px solid var(--ink);
    text-decoration: none;
    color: var(--ink);
    background: var(--paper);
    min-width: 210px;
    text-align: center;
    transition: background 0.15s;
  }
  .tree-card:hover {
    background: var(--n100);
  }
  .tree-card.current {
    background: var(--ink);
    color: var(--paper);
    border-color: var(--ink);
    padding: 22px 30px;
  }
  .tree-card.up {
    border-bottom: 3px solid var(--accent);
  }
  .tree-card.down {
    border-top: 3px solid var(--accent);
  }
  .t-name {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 18px;
    line-height: 1.15;
  }
  .tree-card.current .t-name {
    font-size: 26px;
  }
  .t-zh {
    font-family: 'Lora', serif;
    font-style: italic;
    font-size: 13px;
    margin-top: 2px;
    color: var(--n600);
  }
  .tree-card.current .t-zh {
    color: var(--muted);
  }
  .t-stats {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    margin-top: 6px;
    color: var(--n500);
    letter-spacing: 0.06em;
  }
  .tree-card.current .t-stats {
    color: var(--muted);
  }
  .t-conf {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    color: var(--accent);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.15em;
  }
  .tree-conn {
    font-family: 'JetBrains Mono', monospace;
    color: var(--n400);
    font-size: 20px;
    line-height: 1;
  }
  .tree-empty {
    text-align: center;
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n500);
    line-height: 1.7;
    max-width: 60ch;
    margin: 40px auto;
  }
  .tree-empty code {
    background: var(--n100);
    padding: 1px 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-style: normal;
  }
</style>
