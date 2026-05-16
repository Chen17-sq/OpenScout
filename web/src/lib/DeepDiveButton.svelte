<script lang="ts">
  // "深挖 / Deep Dive" — kicks off the 5-source intensive enrichment for this
  // researcher. The button is most valuable on sparse auto-discovered pages
  // where the user would otherwise bounce. After completion, the page
  // reloads via `invalidateAll()` so the fresh data renders.

  import { invalidateAll } from '$app/navigation';
  import { API_BASE } from '$lib/api';
  import { t } from '$lib/i18n';

  let {
    slug,
    lastRunAt = null,
    sourcesUsed = {},
  }: {
    slug: string;
    lastRunAt?: string | null;
    sourcesUsed?: Record<string, string>;
  } = $props();

  let running = $state(false);
  let result = $state<null | {
    fields_total: number;
    sources: Record<string, { ran: boolean; ok?: boolean; fields_set?: number; note?: string }>;
  }>(null);
  let error = $state<string | null>(null);

  const sourceCount = $derived(Object.keys(sourcesUsed).length);
  const formattedDate = $derived(
    lastRunAt ? new Date(lastRunAt).toISOString().slice(0, 10) : null,
  );

  async function run(force = false) {
    running = true;
    error = null;
    result = null;
    try {
      const res = await fetch(`${API_BASE}/researchers/${slug}/deep-dive${force ? '?force=true' : ''}`, {
        method: 'POST',
      });
      if (!res.ok) {
        error = `HTTP ${res.status}`;
        return;
      }
      result = await res.json();
      // Refresh the page data so the new bio / papers / scores render
      await invalidateAll();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      running = false;
    }
  }
</script>

<div class="dd">
  <button
    class="btn"
    disabled={running}
    onclick={() => run(formattedDate !== null)}
    title={formattedDate
      ? $t('deepDive.titleStale').replace('{date}', formattedDate)
      : $t('deepDive.titleFresh')}
  >
    {#if running}
      <span class="spin">⟳</span> {$t('deepDive.running')}
    {:else}
      🔍 {$t('deepDive.label')}
    {/if}
  </button>

  {#if formattedDate}
    <span class="freshness">
      {$t('deepDive.lastRun')} {formattedDate} · {sourceCount} {$t('deepDive.sources')}
    </span>
  {/if}

  {#if result}
    <div class="result" class:err={error}>
      {#if error}
        ✗ {error}
      {:else}
        ✓ {$t('deepDive.done')}: +{result.fields_total} {$t('deepDive.fields')}
        <ul>
          {#each Object.entries(result.sources) as [name, info]}
            <li>
              {info.ran ? (info.ok ? '✓' : '✗') : '·'}
              <code>{name}</code>
              <span class="note">{info.note}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>

<style>
  .dd {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    padding: 10px 28px;
    border-bottom: 1px solid var(--muted);
    background: var(--n100);
  }
  .btn {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    background: var(--ink);
    color: var(--paper);
    border: none;
    padding: 7px 16px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn:hover:not(:disabled) {
    background: var(--accent);
  }
  .btn:disabled {
    opacity: 0.65;
    cursor: progress;
  }
  .spin {
    display: inline-block;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    100% {
      transform: rotate(360deg);
    }
  }
  .freshness {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    color: var(--n600);
  }
  .result {
    flex-basis: 100%;
    margin-top: 4px;
    padding: 8px 12px;
    border: 1px dashed var(--n400);
    background: var(--paper);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--n700);
  }
  .result.err {
    color: #c0392b;
  }
  .result ul {
    margin: 6px 0 0;
    padding-left: 18px;
    list-style: none;
  }
  .result li {
    line-height: 1.6;
  }
  .result code {
    color: var(--ink);
    font-weight: 600;
  }
  .result .note {
    color: var(--n500);
    margin-left: 6px;
  }
</style>
