<script lang="ts">
  import { t } from '$lib/i18n';
  import { roleLabel } from '$lib/api';

  let { data } = $props();
</script>

<section>
  <div class="section-head">
    <div class="label">Compare</div>
    <div class="h">{$t('researcher.sectionLabel')} ⇄ {$t('researcher.sectionLabel')}</div>
    <div class="meta">side-by-side</div>
  </div>

  {#if !data.a || !data.b}
    <div class="story-card">
      <div></div>
      <div>
        <p class="blurb">
          Compare two researchers by visiting <code>/compare?a=&lt;slug-a&gt;&amp;b=&lt;slug-b&gt;</code>.
        </p>
        <p class="blurb">
          Example: <a href="/compare?a=jun-zhu&b=he-wang">/compare?a=jun-zhu&amp;b=he-wang</a>
        </p>
      </div>
      <div></div>
    </div>
  {:else}
    {@const a = data.a}
    {@const b = data.b}
    <div class="cmp-grid">
      <div class="cmp-cell">
        <h2 class="cmp-name">
          <a href={`/researchers/${a.slug}`}>{a.name_en}</a>
          {#if a.name_zh}<span class="zh"> · {a.name_zh}</span>{/if}
        </h2>
        <div class="cmp-aff">{a.current_affiliation?.name ?? '—'}</div>
        <div class="cmp-role">{roleLabel(a.current_role)} {a.country ?? ''}</div>
      </div>
      <div class="cmp-cell">
        <h2 class="cmp-name">
          <a href={`/researchers/${b.slug}`}>{b.name_en}</a>
          {#if b.name_zh}<span class="zh"> · {b.name_zh}</span>{/if}
        </h2>
        <div class="cmp-aff">{b.current_affiliation?.name ?? '—'}</div>
        <div class="cmp-role">{roleLabel(b.current_role)} {b.country ?? ''}</div>
      </div>
    </div>

    <table class="cmp-table">
      <tbody>
        <tr>
          <th>Citations</th>
          <td class="big" class:winner={(a.citation_count ?? 0) > (b.citation_count ?? 0)}>{(a.citation_count ?? 0).toLocaleString()}</td>
          <td class="big" class:winner={(b.citation_count ?? 0) > (a.citation_count ?? 0)}>{(b.citation_count ?? 0).toLocaleString()}</td>
        </tr>
        <tr>
          <th>h-index</th>
          <td class="big" class:winner={(a.h_index ?? 0) > (b.h_index ?? 0)}>{a.h_index ?? '—'}</td>
          <td class="big" class:winner={(b.h_index ?? 0) > (a.h_index ?? 0)}>{b.h_index ?? '—'}</td>
        </tr>
        <tr>
          <th>Works</th>
          <td>{a.works_count ?? '—'}</td>
          <td>{b.works_count ?? '—'}</td>
        </tr>
        <tr>
          <th>Person score</th>
          <td class:winner={(a.person_score ?? 0) > (b.person_score ?? 0)}>{a.person_score?.toFixed(3) ?? '—'}</td>
          <td class:winner={(b.person_score ?? 0) > (a.person_score ?? 0)}>{b.person_score?.toFixed(3) ?? '—'}</td>
        </tr>
        <tr>
          <th>Trajectory</th>
          <td>{a.trajectory_score?.toFixed(3) ?? '—'}</td>
          <td>{b.trajectory_score?.toFixed(3) ?? '—'}</td>
        </tr>
        <tr>
          <th>Investability</th>
          <td class:winner={(a.investability_score ?? 0) > (b.investability_score ?? 0)}>{a.investability_score?.toFixed(3) ?? '—'}</td>
          <td class:winner={(b.investability_score ?? 0) > (a.investability_score ?? 0)}>{b.investability_score?.toFixed(3) ?? '—'}</td>
        </tr>
        <tr>
          <th>Signature paper</th>
          <td>{a.signature_paper?.title ?? '—'}</td>
          <td>{b.signature_paper?.title ?? '—'}</td>
        </tr>
        <tr>
          <th>Tags</th>
          <td>
            {#each (a.tags ?? []).slice(0, 5) as t_}<span class="badge">{t_.label}</span>{/each}
          </td>
          <td>
            {#each (b.tags ?? []).slice(0, 5) as t_}<span class="badge">{t_.label}</span>{/each}
          </td>
        </tr>
        <tr>
          <th>Projects</th>
          <td>
            <ul class="plist">
              {#each (a.projects ?? []) as p}<li>{p.name}{p.role ? ` · ${p.role}` : ''}</li>{/each}
            </ul>
          </td>
          <td>
            <ul class="plist">
              {#each (b.projects ?? []) as p}<li>{p.name}{p.role ? ` · ${p.role}` : ''}</li>{/each}
            </ul>
          </td>
        </tr>
      </tbody>
    </table>
  {/if}
</section>

<style>
  .cmp-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    border-bottom: 4px solid var(--ink);
  }
  .cmp-cell {
    padding: 26px 28px;
    border-right: 1px solid var(--ink);
  }
  .cmp-cell:last-child {
    border-right: none;
  }
  .cmp-name {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 40px;
    margin: 0 0 8px;
    line-height: 1.1;
  }
  .cmp-name a {
    color: var(--ink);
    text-decoration: none;
  }
  .cmp-name a:hover {
    color: var(--accent);
  }
  .cmp-name .zh {
    color: var(--n600);
    font-weight: 700;
  }
  .cmp-aff {
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n700);
    font-size: 16px;
  }
  .cmp-role {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--n500);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .cmp-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'Lora', serif;
    font-size: 15px;
  }
  .cmp-table th {
    width: 22%;
    padding: 18px 22px;
    text-align: left;
    background: var(--n100);
    border-bottom: 1px solid var(--muted);
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--n500);
    vertical-align: top;
  }
  .cmp-table td {
    padding: 18px 22px;
    border-bottom: 1px solid var(--muted);
    border-left: 1px solid var(--muted);
    vertical-align: top;
  }
  .cmp-table td.big {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 32px;
    line-height: 1;
  }
  .cmp-table td.winner {
    background: var(--paper);
    color: var(--accent);
  }
  .plist {
    list-style: none;
    padding: 0;
    margin: 0;
    font-size: 13px;
  }
  .plist li {
    line-height: 1.6;
  }
</style>
