<script lang="ts">
  import { t } from '$lib/i18n';
  import { arxivUrl, blurb, roleLabel } from '$lib/api';
  import StarButton from '$lib/StarButton.svelte';
  import SourceBadge from '$lib/SourceBadge.svelte';
  import DeepDiveButton from '$lib/DeepDiveButton.svelte';
  import { compareSlots, addToCompare, COMPARE_MAX } from '$lib/watchlist';

  let { data } = $props();
  const r = $derived(data.researcher);
  const inCompare = $derived($compareSlots.includes(r.slug));
  const compareFull = $derived($compareSlots.length >= COMPARE_MAX && !inCompare);
  const firstAuthored = $derived(r.papers.filter((p) => p.position === 1));
  const coAuthored = $derived(r.papers.filter((p) => p.position !== 1));

  const flag = (cc: string | null) => {
    if (!cc) return '';
    return cc.toUpperCase().replace(/./g, (c) => String.fromCodePoint(0x1f1a5 + c.charCodeAt(0)));
  };
</script>

<section>
  <div class="section-head">
    <div class="label">{$t('researcher.sectionLabel')}</div>
    <div class="h">
      {#if r.photo_url}<img class="profile-photo" src={r.photo_url} alt={r.name_en} />{/if}
      {r.name_en}
    </div>
    <div class="meta">
      {r.name_zh ?? ''}
      <span class="star-wrap"><StarButton slug={r.slug} /></span>
      <button
        type="button"
        class="cmp-btn"
        class:on={inCompare}
        onclick={() => addToCompare(r.slug)}
        disabled={compareFull}
        title={inCompare
          ? $t('watchlist.inCompare')
          : compareFull
            ? $t('watchlist.compareFull')
            : $t('watchlist.addToCompare')}
        aria-label={$t('watchlist.addToCompare')}
      >
        {#if inCompare}✓ compare{:else}➕ compare{/if}
      </button>
    </div>
  </div>

  <DeepDiveButton
    slug={r.slug}
    lastRunAt={r.deep_dive_run_at}
    sourcesUsed={r.deep_dive_sources_used}
  />

  <div class="profile-grid">
    <div>
      <div class="lbl">{$t('researcher.stage')}</div>
      <div class="val">
        {roleLabel(r.current_role) || '—'}<SourceBadge source={r.role_source} />
      </div>
      {#if r.career_stage_year}<div class="sub">Year {r.career_stage_year}</div>{/if}
    </div>
    <div>
      <div class="lbl">{$t('researcher.affiliation')}</div>
      <div class="val">
        {r.current_affiliation?.name ?? '—'}<SourceBadge source={r.affiliation_source} />
      </div>
      {#if r.current_affiliation?.name_zh}
        <div class="sub">{r.current_affiliation.name_zh}</div>
      {/if}
    </div>
    <div>
      <div class="lbl">{$t('researcher.affiliationCountry')}</div>
      <div class="val">
        {r.country ? `${flag(r.country)} ${r.country}` : '—'}<SourceBadge
          source={r.country_source}
        />
      </div>
    </div>
    <div>
      <div class="lbl">{$t('researcher.advisor')}</div>
      {#if r.advisor}
        <a class="val" href={`/researchers/${r.advisor.slug}`}>{r.advisor.name_en}</a>
        {#if r.advisor.name_zh}<div class="sub">{r.advisor.name_zh}</div>{/if}
      {:else if r.inferred_advisors.length}
        <a class="val" href={`/researchers/${r.inferred_advisors[0].slug}`}>
          {r.inferred_advisors[0].name_en}
        </a>
        <div class="sub italic">({$t('researcher.inferredAdvisor')})</div>
      {:else}
        <div class="val">—</div>
      {/if}
    </div>
  </div>

  <div class="stats-band">
    <div>
      <span class="num">{r.h_index ?? '—'}</span>
      <span class="lbl">{$t('researcher.hIndex')}</span>
    </div>
    <div class="accent">
      <span class="num">{(r.citation_count ?? 0).toLocaleString()}</span>
      <span class="lbl">{$t('researcher.citation')}</span>
    </div>
    <div>
      <span class="num">{r.works_count ?? r.papers.length}</span>
      <span class="lbl">{$t('researcher.works')}</span>
    </div>
    <div>
      {#if r.confidence_level === 'high'}
        <span class="badge anchor">{$t('researcher.confHigh')}</span>
      {:else if r.confidence_level === 'medium'}
        <span class="badge">{$t('researcher.confMedium')}</span>
      {:else}
        <span class="badge">{$t('researcher.confLow')}</span>
      {/if}
    </div>
  </div>

  <div class="contact-row">
    {#if r.homepage_url}<a class="badge" href={r.homepage_url} target="_blank" rel="noreferrer">{$t('researcher.homepage')} ↗</a>{/if}
    {#if r.twitter_handle}<a class="badge" href={`https://x.com/${r.twitter_handle}`} target="_blank" rel="noreferrer">@{r.twitter_handle}</a>{/if}
    {#if r.github_handle}<a class="badge" href={`https://github.com/${r.github_handle}`} target="_blank" rel="noreferrer">{$t('researcher.github')}</a>{/if}
    {#if r.zhihu_url}<a class="badge" href={r.zhihu_url} target="_blank" rel="noreferrer">{$t('researcher.zhihu')}</a>{/if}
    {#if r.orcid}<a class="badge" href={r.orcid} target="_blank" rel="noreferrer">ORCID</a>{/if}
    {#if r.openalex_id}<a class="badge" href={r.openalex_id} target="_blank" rel="noreferrer">OpenAlex</a>{/if}
  </div>

  {#if r.bio}
    <div class="bio-block">
      <div class="lbl-mini">{$t('researcher.bio')}</div>
      <p>{r.bio}</p>
    </div>
  {/if}

  {#if r.tags?.length}
    {@const signalTags = r.tags.filter((t) => t.type === 'signal')}
    {@const instTags = r.tags.filter((t) => t.type === 'institution')}
    {@const topicTags = r.tags
      .filter((t) => !t.type || t.type === 'topic')
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))}
    <div class="bio-block">
      <div class="lbl-mini">{$t('researcher.researchDirections')}</div>
      <div class="tag-list">
        {#each signalTags as tag}
          <span class="tag t-signal" title={tag.source ?? ''}>
            {tag.label_zh ?? tag.label}
          </span>
        {/each}
        {#each instTags as tag}
          <a class="tag t-institution" href={`/institutions`}>
            {tag.label}
            {#if tag.country}<span class="tag-meta">{tag.country}</span>{/if}
          </a>
        {/each}
        {#each topicTags as tag}
          <a
            class="tag t-topic"
            class:t-generic={(tag.level ?? 0) === 0}
            href={`/tags/${encodeURIComponent(tag.label)}`}
          >
            {tag.label}
            <span class="tag-score">{tag.score.toFixed(2)}</span>
          </a>
        {/each}
      </div>
    </div>
  {/if}

  {#if r.projects?.length}
    <div class="bio-block">
      <div class="lbl-mini">{$t('researcher.projects')}</div>
      <ul class="project-list">
        {#each r.projects as p}
          <li>
            {#if p.url}
              <a href={p.url} target="_blank" rel="noreferrer">{p.name}</a>
            {:else}{p.name}{/if}
            {#if p.role}<span class="role">· {p.role}</span>{/if}
            {#if p.category}<span class="cat">[{p.category}]</span>{/if}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if r.signature_paper}
    <div class="section-head">
      <div class="label">Featured</div>
      <div class="h">{$t('researcher.signaturePaper')}</div>
      <div class="meta">{r.signature_paper.citation_count.toLocaleString()} cites</div>
    </div>
    <article class="story-card">
      <div class="no">★</div>
      <div>
        <a class="title" href={arxivUrl(r.signature_paper.arxiv_id)} target="_blank" rel="noreferrer">
          {r.signature_paper.title}
        </a>
        {#if r.signature_paper.abstract}<div class="blurb">{blurb(r.signature_paper.abstract, 280)}</div>{/if}
      </div>
      <div class="right">
        <span class="v">{r.signature_paper.citation_count}</span>
        <div>cites</div>
      </div>
    </article>
  {/if}

  {#if r.students.length}
    <div class="section-head">
      <div class="label">Lineage</div>
      <div class="h">{$t('researcher.students')}</div>
      <div class="meta">{r.students.length}</div>
    </div>
    <table class="board-table">
      <tbody>
        {#each r.students as s}
          <tr>
            <td><a href={`/researchers/${s.slug}`}>{s.name_en}</a>{#if s.name_zh} · {s.name_zh}{/if}</td>
            <td class="font-mono text-xs">{roleLabel(s.current_role) || '—'}</td>
            <td class="font-mono text-xs text-right">h={s.h_index ?? '—'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}

  <div class="section-head">
    <div class="label">Output</div>
    <div class="h">{$t('researcher.firstAuthorPapers')}</div>
    <div class="meta">{firstAuthored.length} / {r.papers.length}</div>
  </div>

  {#if firstAuthored.length === 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">{$t('researcher.noFirstAuthor')}</div>
      <div></div>
    </div>
  {:else}
    {#each firstAuthored as p, i}
      <article class="story-card">
        <div class="no">{String(i + 1).padStart(2, '0')}</div>
        <div>
          <a class="title" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.title}</a>
          <div class="by">
            {p.venue ?? 'arXiv'} · {p.published_at ?? 'TBD'}
            {#if p.topics.length}· {p.topics.join(' / ')}{/if}
            {#if (p.citation_count ?? 0) > 0}· {p.citation_count} cites{/if}
          </div>
          {#if p.abstract}<div class="blurb">{blurb(p.abstract, 240)}</div>{/if}
          {#if p.author_emails && p.author_emails.length}
            <details class="emails">
              <summary>📧 {p.author_emails.length} contact{p.author_emails.length === 1 ? '' : 's'} found in PDF</summary>
              <ul>
                {#each p.author_emails as em}
                  <li><code>{em}</code></li>
                {/each}
              </ul>
            </details>
          {/if}
        </div>
        <div class="right">
          <a class="v" href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.arxiv_id ?? '—'}</a>
        </div>
      </article>
    {/each}
  {/if}

  {#if coAuthored.length}
    <div class="section-head">
      <div class="label">Output</div>
      <div class="h">{$t('researcher.coAuthored')}</div>
      <div class="meta">{coAuthored.length}</div>
    </div>
    <table class="board-table">
      <thead>
        <tr>
          <th>Title</th>
          <th>#</th>
          <th>Topics</th>
          <th>arXiv</th>
        </tr>
      </thead>
      <tbody>
        {#each coAuthored as p}
          <tr>
            <td><a href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.title}</a></td>
            <td class="font-mono text-xs">#{p.position}</td>
            <td class="font-mono text-xs">{p.topics.join(', ') || '—'}</td>
            <td class="font-mono text-xs"><a href={arxivUrl(p.arxiv_id)} target="_blank" rel="noreferrer">{p.arxiv_id ?? '—'}</a></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  .profile-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border-bottom: 1px solid var(--ink);
  }
  .profile-grid > div {
    padding: 18px 22px;
    border-right: 1px solid var(--muted);
  }
  .profile-grid > div:last-child {
    border-right: none;
  }
  .profile-grid .lbl {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--n500);
    margin-bottom: 6px;
  }
  .profile-grid .val {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 20px;
    line-height: 1.2;
    color: var(--ink);
    text-decoration: none;
    display: block;
  }
  .profile-grid a.val:hover {
    color: var(--accent);
  }
  .profile-grid .sub {
    font-family: 'Lora', serif;
    font-size: 12px;
    color: var(--n600);
    margin-top: 4px;
  }
  .stats-band {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border-bottom: 4px solid var(--ink);
    background: var(--paper);
  }
  .stats-band > div {
    padding: 22px 18px;
    border-right: 1px solid var(--ink);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .stats-band > div:last-child {
    border-right: none;
  }
  .stats-band .num {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: 42px;
    line-height: 1;
    color: var(--ink);
  }
  .stats-band .accent .num {
    color: var(--accent);
  }
  .stats-band .lbl {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--n500);
  }
  .contact-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 18px 28px;
    border-bottom: 1px solid var(--ink);
  }
  .bio-block {
    padding: 18px 28px;
    border-bottom: 1px solid var(--ink);
  }
  .lbl-mini {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--n500);
    margin-bottom: 10px;
  }
  .bio-block p {
    font-family: 'Lora', serif;
    font-size: 15.5px;
    line-height: 1.65;
    color: var(--n700);
    font-style: italic;
    margin: 0;
  }
  .tag-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--ink);
    padding: 4px 9px;
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: var(--ink);
    text-decoration: none;
  }
  .tag:hover {
    background: var(--ink);
    color: var(--paper);
  }
  .tag-score {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    font-weight: 500;
    color: var(--n500);
  }
  .tag:hover .tag-score {
    color: var(--paper);
    opacity: 0.7;
  }
  /* Signal: amber chip, draws the eye first */
  .tag.t-signal {
    background: #fffaf0;
    border: 1px dashed #b8860b;
    color: #8a6300;
    cursor: help;
  }
  .tag.t-signal:hover {
    background: #b8860b;
    color: var(--paper);
  }
  /* Institution: solid ink chip */
  .tag.t-institution {
    background: var(--ink);
    color: var(--paper);
    border-color: var(--ink);
  }
  .tag.t-institution:hover {
    background: var(--accent);
    border-color: var(--accent);
  }
  .tag-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    opacity: 0.75;
    margin-left: 2px;
  }
  /* Generic topic tags (level=0 OpenAlex catch-alls): faded */
  .tag.t-topic.t-generic {
    border-color: var(--n400);
    color: var(--n500);
  }
  .tag.t-topic.t-generic .tag-score {
    color: var(--n400);
  }
  .project-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .project-list li {
    font-family: 'Lora', serif;
    font-size: 15px;
    line-height: 1.8;
  }
  .project-list a {
    color: var(--ink);
    text-decoration: underline;
    text-decoration-color: var(--n400);
    font-weight: 600;
  }
  .project-list a:hover {
    color: var(--accent);
  }
  .project-list .role {
    color: var(--n600);
    font-style: italic;
  }
  .project-list .cat {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--n500);
    margin-left: 6px;
  }
  .star-wrap {
    display: inline-block;
    margin-left: 12px;
  }
  .cmp-btn {
    background: transparent;
    border: 1px solid var(--n400);
    color: var(--n600);
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
    margin-left: 6px;
    cursor: pointer;
    line-height: 1.2;
  }
  .cmp-btn:hover:not(:disabled) {
    border-color: var(--ink);
    color: var(--ink);
  }
  .cmp-btn.on {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--paper);
  }
  .cmp-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .profile-photo {
    display: inline-block;
    width: 56px;
    height: 56px;
    object-fit: cover;
    border: 2px solid var(--ink);
    vertical-align: middle;
    margin-right: 14px;
  }
  .emails {
    margin-top: 10px;
    padding: 8px 12px;
    border: 1px dashed var(--n400);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
  }
  .emails summary {
    cursor: pointer;
    color: var(--accent);
    font-weight: 600;
    list-style: none;
  }
  .emails summary::-webkit-details-marker {
    display: none;
  }
  .emails ul {
    margin: 8px 0 0;
    padding-left: 18px;
    list-style: square;
  }
  .emails li {
    color: var(--ink);
    line-height: 1.6;
  }
  .emails code {
    background: var(--n100);
    padding: 1px 6px;
    user-select: all;
  }
</style>
