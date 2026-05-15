<script lang="ts">
  let { data } = $props();
</script>

<section>
  <div class="section-head">
    <div class="label">Archive</div>
    <div class="h">Past Editions</div>
    <div class="meta">{data.briefs.length} issues</div>
  </div>

  {#if data.briefs.length === 0}
    <div class="story-card">
      <div></div>
      <div class="blurb">No briefs yet. Run <code>make brief</code>.</div>
      <div></div>
    </div>
  {:else}
    <table class="board-table">
      <thead>
        <tr>
          <th>Issue</th>
          <th>Date</th>
          <th>Generated</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each data.briefs as b}
          <tr>
            <td class="font-mono">VOL. {b.volume} · NO. {String(b.issue).padStart(3, '0')}</td>
            <td class="font-display text-lg">{b.brief_date}</td>
            <td class="font-mono text-xs text-n500">{b.generated_at?.slice(0, 19) ?? '—'}</td>
            <td><a href={`/daily/${b.brief_date}`}>Read →</a></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>
