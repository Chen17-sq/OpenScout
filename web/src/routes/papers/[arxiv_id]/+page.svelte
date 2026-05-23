<script lang="ts">
  import { arxivUrl, roleLabel } from '$lib/api';

  let { data } = $props();
  const p = $derived(data.paper);

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };
</script>

<section>
  <div class="section-head">
    <div class="label">Paper</div>
    <div class="h">{p.title}</div>
    <div class="meta">arXiv:{p.arxiv_id ?? '—'}</div>
  </div>

  <div class="meta-band">
    <div class="bm">
      <div class="lbl">Venue</div>
      <div class="val">{p.venue ?? 'arXiv'}</div>
    </div>
    <div class="bm">
      <div class="lbl">Published</div>
      <div class="val mono">{p.published_at ?? p.first_seen_at?.slice(0, 10) ?? '—'}</div>
    </div>
    <div class="bm">
      <div class="lbl">Citations</div>
      <div class="val mono accent">{(p.citation_count ?? 0).toLocaleString()}</div>
    </div>
    <div class="bm">
      <div class="lbl">GitHub ★</div>
      <div class="val mono">{p.github_stars ?? '—'}</div>
    </div>
    <div class="bm">
      <div class="lbl">Buzz</div>
      <div class="val mono">{p.buzz_score != null ? p.buzz_score.toFixed(2) : (p.work_score != null ? p.work_score.toFixed(2) : '—')}</div>
    </div>
  </div>

  {#if p.one_liner_zh}
    <div class="one-liner">{p.one_liner_zh}</div>
  {/if}

  <div class="links">
    {#if p.pdf_url}<a class="badge" href={p.pdf_url} target="_blank" rel="noreferrer">PDF</a>{/if}
    {#if p.code_url}<a class="badge" href={p.code_url} target="_blank" rel="noreferrer">Code ↗</a>{/if}
    {#if p.openalex_id}<a class="badge" href={p.openalex_id} target="_blank" rel="noreferrer">OpenAlex</a>{/if}
    {#if p.arxiv_id}<a class="badge" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">arXiv ↗</a>{/if}
  </div>

  {#if p.abstract}
    <div class="abstract">
      <div class="lbl-mini">Abstract</div>
      <p>{p.abstract}</p>
    </div>
  {/if}

  {#if p.authors.length}
  <div class="section-head">
    <div class="label">Roster</div>
    <div class="h">Authors</div>
    <div class="meta">{p.authors.length} · ordered</div>
  </div>

  <table class="board-table">
    <tbody>
      {#each p.authors as a}
        <tr>
          <td class="font-mono text-xs">#{a.position}</td>
          <td>
            <a href={`/researchers/${a.slug}`}>{a.name_en}</a>
            {#if a.name_zh}<span class="text-n500 font-serif"> · {a.name_zh}</span>{/if}
          </td>
          <td class="font-mono text-xs">{a.country ? `${flag(a.country)} ${a.country}` : '—'}</td>
          <td class="font-mono text-xs">{roleLabel(a.current_role)}</td>
          <td class="text-right font-mono">h={a.h_index ?? '—'}</td>
          <td class="text-right font-mono">{(a.citation_count ?? 0).toLocaleString()}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  {/if}

  {#if p.topics.length}
    <div class="topics-row">
      <span class="lbl-mini">Topics:</span>
      {#each p.topics as t}
        <a class="badge" href={`/topics/${t.slug}`}>{t.name}</a>
      {/each}
    </div>
  {/if}

  {#if p.author_emails.length}
    <div class="emails-block">
      <div class="lbl-mini">📧 Contacts (extracted from PDF)</div>
      <ul>
        {#each p.author_emails as em}
          <li><code>{em}</code></li>
        {/each}
      </ul>
    </div>
  {/if}
</section>

<style>
  .meta-band {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    border-bottom: 4px solid var(--ink);
  }
  .bm {
    padding: 18px 18px;
    border-right: 1px solid var(--ink);
  }
  .bm:last-child {
    border-right: none;
  }
  .bm .lbl {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--n500);
    margin-bottom: 6px;
  }
  .bm .val {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 22px;
  }
  .bm .val.mono {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
  }
  .bm .val.accent {
    color: var(--accent);
  }
  .one-liner {
    padding: 18px 28px;
    font-family: 'Lora', serif;
    font-style: italic;
    font-size: 17px;
    color: var(--n700);
    border-bottom: 1px solid var(--muted);
  }
  .links {
    padding: 12px 28px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    border-bottom: 1px solid var(--muted);
  }
  .abstract {
    padding: 22px 28px;
    border-bottom: 1px solid var(--ink);
  }
  .abstract p {
    font-family: 'Lora', serif;
    font-size: 15px;
    line-height: 1.7;
    margin: 8px 0 0;
    color: var(--n700);
  }
  .lbl-mini {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--n500);
  }
  .topics-row {
    padding: 18px 28px;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
    border-top: 1px solid var(--muted);
  }
  .topics-row .badge {
    text-decoration: none;
  }
  .emails-block {
    padding: 18px 28px;
    border-top: 1px solid var(--muted);
  }
  .emails-block ul {
    margin: 10px 0 0;
    list-style: square;
    padding-left: 20px;
  }
  .emails-block code {
    background: var(--n100);
    padding: 1px 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    user-select: all;
  }
</style>
