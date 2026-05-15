<script lang="ts">
  import { t } from './i18n';
  import { roleLabel } from './api';

  type Tag = { label: string; score?: number; level?: number };
  type Project = { name: string; role?: string; category?: string; url?: string };

  let {
    r,
    compact = false,
  }: {
    r: {
      slug: string;
      name_en: string;
      name_zh: string | null;
      current_role: string | null;
      country: string | null;
      confidence_level: string;
      h_index: number | null;
      citation_count: number | null;
      n_papers?: number;
      tags?: Tag[];
      projects?: Project[];
    };
    compact?: boolean;
  } = $props();

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc
      .toUpperCase()
      .replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };
</script>

<article class="r-card" class:compact>
  <header>
    <h3>
      <a href={`/researchers/${r.slug}`}>{r.name_en}</a>{#if r.name_zh}<span class="zh">{' · '}{r.name_zh}</span>{/if}
    </h3>
    <div class="meta-row">
      {#if r.country}<span class="flag" aria-label={r.country}>{flag(r.country)} {r.country}</span>{/if}
      {#if r.current_role}<span class="badge">{roleLabel(r.current_role)}</span>{/if}
      {#if r.confidence_level === 'high'}
        <span class="badge anchor">{$t('researcher.confHigh')}</span>
      {:else if r.confidence_level === 'medium'}
        <span class="badge">{$t('researcher.confMedium')}</span>
      {:else}
        <span class="badge auto">{$t('researcher.confLow')}</span>
      {/if}
    </div>
  </header>

  <div class="stats">
    <div>
      <span class="num">{r.h_index ?? '—'}</span>
      <span class="lbl">{$t('researcher.hIndex')}</span>
    </div>
    <div>
      <span class="num">{(r.citation_count ?? 0).toLocaleString()}</span>
      <span class="lbl">{$t('researcher.citation')}</span>
    </div>
    {#if r.n_papers !== undefined}
      <div>
        <span class="num">{r.n_papers}</span>
        <span class="lbl">{$t('researcher.firstAuthorPapers').toLowerCase().includes('paper') ? 'papers' : '论文'}</span>
      </div>
    {/if}
  </div>

  {#if r.tags && r.tags.length}
    <div class="tags">
      {#each r.tags.slice(0, 5) as tag}
        <a href={`/tags/${encodeURIComponent(tag.label)}`} class="tag">{tag.label}</a>
      {/each}
    </div>
  {/if}

  {#if r.projects && r.projects.length}
    <div class="projects">
      <div class="projects-label">{$t('researcher.projects')}</div>
      <ul>
        {#each r.projects as p}
          <li>
            {#if p.url}<a href={p.url} target="_blank" rel="noreferrer">{p.name}</a>{:else}{p.name}{/if}
            {#if p.role}<span class="role">· {p.role}</span>{/if}
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</article>

<style>
  .r-card {
    padding: 18px 22px;
    border-bottom: 1px solid var(--muted);
  }
  .r-card h3 {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 22px;
    margin: 0 0 4px;
    line-height: 1.15;
  }
  .r-card h3 a {
    color: var(--ink);
    text-decoration: none;
  }
  .r-card h3 a:hover {
    color: var(--accent);
  }
  .r-card h3 .zh {
    color: var(--n600);
    font-weight: 600;
  }
  .meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
    font-size: 10.5px;
  }
  .flag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n600);
    letter-spacing: 0.08em;
  }
  .stats {
    display: flex;
    gap: 22px;
    padding: 10px 0 12px;
    border-top: 1px solid var(--muted);
    border-bottom: 1px solid var(--muted);
    margin-bottom: 10px;
  }
  .stats > div {
    display: flex;
    flex-direction: column;
  }
  .stats .num {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 22px;
    color: var(--ink);
    line-height: 1;
  }
  .stats .lbl {
    font-family: 'Inter', sans-serif;
    font-size: 9.5px;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--n500);
    margin-top: 3px;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin: 4px 0 10px;
  }
  .tag {
    display: inline-block;
    border: 1px solid var(--ink);
    padding: 2px 7px;
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--ink);
    text-decoration: none;
    transition: background 0.1s;
  }
  .tag:hover {
    background: var(--ink);
    color: var(--paper);
  }
  .projects {
    margin-top: 6px;
  }
  .projects-label {
    font-family: 'Inter', sans-serif;
    font-size: 9.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--n500);
    margin-bottom: 4px;
  }
  .projects ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .projects li {
    font-family: 'Lora', serif;
    font-size: 13px;
    color: var(--ink);
    line-height: 1.5;
  }
  .projects li a {
    color: var(--ink);
    text-decoration: underline;
    text-decoration-color: var(--n400);
  }
  .projects li a:hover {
    color: var(--accent);
    text-decoration-color: var(--accent);
  }
  .projects li .role {
    color: var(--n500);
    font-style: italic;
  }
  .badge.auto {
    color: var(--n500);
    border-color: var(--n400);
  }
</style>
