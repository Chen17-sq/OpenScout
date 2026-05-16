<script lang="ts">
  // Renders the provenance of an inferred field (country / role / affiliation).
  // - "manual" / "openalex" / "arxiv_html" → verified (ink badge)
  // - "surname_pinyin" / "peer_inheritance" → inferred (dashed amber badge)
  // - null → renders nothing
  //
  // The point: the user should be able to glance at any researcher and tell at
  // once whether the country/role we show was extracted from an authoritative
  // source, or guessed from a co-author / surname.

  import { t } from '$lib/i18n';

  let { source }: { source: string | null | undefined } = $props();

  const verified = $derived(
    source === 'manual' || source === 'openalex' || source === 'arxiv_html',
  );

  const labelKey = $derived(
    {
      manual: 'researcher.sourceManual',
      openalex: 'researcher.sourceOpenalex',
      surname_pinyin: 'researcher.sourceSurname',
      peer_inheritance: 'researcher.sourcePeer',
      arxiv_html: 'researcher.sourceArxivHtml',
    }[source ?? ''] ?? null,
  );

  const titleKey = $derived(
    verified ? 'researcher.sourceVerifiedTitle' : 'researcher.sourceInferredTitle',
  );
</script>

{#if source && labelKey}
  <span class="src" class:verified class:inferred={!verified} title={$t(titleKey)}>
    {$t(labelKey)}
  </span>
{/if}

<style>
  .src {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.05em;
    padding: 1px 5px;
    margin-left: 6px;
    text-transform: uppercase;
    line-height: 1.5;
    vertical-align: 2px;
    cursor: help;
  }
  .verified {
    border: 1px solid var(--ink);
    color: var(--ink);
    background: var(--paper);
  }
  .inferred {
    border: 1px dashed #b8860b;
    color: #8a6300;
    background: #fffaf0;
  }
</style>
