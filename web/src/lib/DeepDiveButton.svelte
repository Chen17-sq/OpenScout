<script lang="ts">
  // "深挖 / Deep Dive" — fires the 11-source intensive enrichment for THIS
  // researcher. v1.12 changes:
  //   * Async — POST returns a job_id immediately; we poll /jobs/{id} until
  //     state is "succeeded" or "failed". UI shows running progress live.
  //   * Quota — server returns 429 + Retry-After when daily limit hit. We
  //     also pre-fetch the quota on mount so the button can show "2 left".

  import { invalidateAll } from '$app/navigation';
  import { API_BASE } from '$lib/api';
  import { t } from '$lib/i18n';
  import { onMount } from 'svelte';

  let {
    slug,
    lastRunAt = null,
    sourcesUsed = {},
  }: {
    slug: string;
    lastRunAt?: string | null;
    sourcesUsed?: Record<string, string>;
  } = $props();

  type Source = { ran: boolean; ok?: boolean; fields_set?: number; note?: string };
  type Result = { fields_total: number; sources: Record<string, Source> };

  let running = $state(false);
  let pollState = $state<string | null>(null); // "queued" | "running"
  let result = $state<Result | null>(null);
  let error = $state<string | null>(null);
  let quota = $state<{ used: number; limit: number; remaining: number } | null>(null);

  const sourceCount = $derived(Object.keys(sourcesUsed).length);
  const formattedDate = $derived(
    lastRunAt ? new Date(lastRunAt).toISOString().slice(0, 10) : null,
  );

  onMount(() => {
    refreshQuota();
  });

  async function refreshQuota() {
    try {
      const res = await fetch(`${API_BASE}/researchers/${slug}/deep-dive/quota`);
      if (res.ok) quota = await res.json();
    } catch {
      /* network down — ignore, button still works */
    }
  }

  async function pollJob(jobId: number): Promise<Result | null> {
    for (let i = 0; i < 60; i++) {
      // up to 60 × 2s = 2 minutes
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`);
        if (!res.ok) {
          error = `Poll HTTP ${res.status}`;
          return null;
        }
        const job = await res.json();
        pollState = job.state;
        if (job.state === 'succeeded') return job.result as Result;
        if (job.state === 'failed') {
          error = job.error ?? 'job failed';
          return null;
        }
        // Still queued / running — keep polling
      } catch (e) {
        error = (e as Error).message;
        return null;
      }
    }
    error = 'timed out after 2 minutes';
    return null;
  }

  async function run(force = false) {
    running = true;
    pollState = null;
    error = null;
    result = null;
    try {
      const url = `${API_BASE}/researchers/${slug}/deep-dive${force ? '?force=true' : ''}`;
      const res = await fetch(url, { method: 'POST' });
      if (res.status === 429) {
        const data = await res.json().catch(() => ({}));
        error = data.detail ?? 'Daily quota reached. Try again after UTC midnight.';
        running = false;
        await refreshQuota();
        return;
      }
      if (!res.ok) {
        error = `HTTP ${res.status}`;
        running = false;
        return;
      }
      const enq = await res.json();
      if (enq.quota) quota = enq.quota;

      // Async path: poll
      if (typeof enq.id === 'number') {
        pollState = enq.state;
        const final = await pollJob(enq.id);
        if (final) result = final;
        await invalidateAll();
      } else {
        // Legacy sync path
        result = enq as Result;
        await invalidateAll();
      }
    } catch (e) {
      error = (e as Error).message;
    } finally {
      running = false;
      pollState = null;
      refreshQuota();
    }
  }
</script>

<div class="dd">
  <button
    class="btn"
    disabled={running || (quota !== null && quota.remaining <= 0)}
    onclick={() => run(formattedDate !== null)}
    title={formattedDate
      ? $t('deepDive.titleStale').replace('{date}', formattedDate)
      : $t('deepDive.titleFresh')}
  >
    {#if running}
      <span class="spin">⟳</span>
      {pollState === 'queued' ? $t('deepDive.queued') : $t('deepDive.running')}
    {:else}
      🔍 {$t('deepDive.label')}
    {/if}
  </button>

  {#if formattedDate}
    <span class="freshness">
      {$t('deepDive.lastRun')} {formattedDate} · {sourceCount} {$t('deepDive.sources')}
    </span>
  {/if}

  {#if quota}
    <span class="quota" class:quota-low={quota.remaining <= 1}>
      {quota.remaining}/{quota.limit} {$t('deepDive.divesLeft')}
    </span>
  {/if}

  {#if error}
    <div class="result err">✗ {error}</div>
  {:else if result}
    {@const sources = Object.entries(result.sources)}
    {@const ranOk = sources.filter(([, info]) => info.ran && info.ok).length}
    {@const noId = sources.filter(([, info]) => info.note?.startsWith('no ')).length}
    {@const cached = sources.filter(([, info]) => !info.ran).length}
    <div class="result">
      <div class="hdr">
        ✓ {$t('deepDive.done')}: +{result.fields_total} {$t('deepDive.fields')}
        {#if cached > 0}<span class="note">· {cached} {$t('deepDive.cached')}</span>{/if}
        {#if noId > 0}<span class="note">· {noId} {$t('deepDive.skippedNoId')}</span>{/if}
      </div>
      <ul>
        {#each sources as [name, info]}
          <li class:dim={!info.ran || (info.note ?? '').startsWith('no ')}>
            {info.ran ? (info.ok ? '✓' : '✗') : '⋯'}
            <code>{name}</code>
            <span class="note">{info.note}</span>
          </li>
        {/each}
      </ul>
      {#if result.fields_total === 0 && ranOk > 0}
        <div class="hint">{$t('deepDive.allCachedHint')}</div>
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
  .quota {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    color: var(--n500);
    padding: 1px 6px;
    border: 1px solid var(--n400);
  }
  .quota-low {
    color: #b8860b;
    border-color: #b8860b;
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
  .result .hdr {
    margin-bottom: 4px;
  }
  .result li.dim {
    color: var(--n500);
    opacity: 0.7;
  }
  .result .hint {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px dotted var(--n400);
    font-style: italic;
    color: var(--n600);
  }
</style>
