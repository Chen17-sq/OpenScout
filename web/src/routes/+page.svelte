<script lang="ts">
  import EditionStrip from '$lib/EditionStrip.svelte';
  import Masthead from '$lib/Masthead.svelte';
  import KpiBand from '$lib/KpiBand.svelte';
  import HeroSection from '$lib/HeroSection.svelte';
  import SectionBlock from '$lib/SectionBlock.svelte';
  import { t } from '$lib/i18n';

  let { data } = $props();
  const brief = $derived(data.brief);
</script>

{#if !brief}
  <Masthead />
  <div class="story-card">
    <div></div>
    <div>
      <div class="title">{$t('backend.offline')}</div>
      <div class="blurb">{$t('backend.offlineHint')}</div>
    </div>
    <div></div>
  </div>
{:else}
  <EditionStrip issue={brief.issue} briefDate={brief.brief_date} />
  <Masthead briefDate={brief.brief_date} issue={brief.issue} />

  <KpiBand kpi={brief.kpi} />

  <HeroSection
    leftItems={brief.new_first_authors}
    rightItems={brief.anchor_activity}
    rightAccent
  />

  <SectionBlock
    label="Section C"
    title={$t('section.soonGraduatingPicks')}
    meta={$t('section.soonGraduatingMeta')}
    items={brief.soon_graduating_picks}
    emptyMessage={$t('section.soonGraduatingEmpty')}
  />

  <SectionBlock
    label="Section D"
    title={$t('section.incomingApPicks')}
    meta="hand-curated · update seeds/researchers.yaml"
    items={brief.incoming_ap_picks}
    emptyMessage={$t('section.incomingApEmpty')}
  />

  <SectionBlock
    label="Section E"
    title={$t('section.hotPapers')}
    meta={$t('section.hotPapersMeta')}
    items={brief.hot_papers}
    emptyMessage={$t('section.hotPapersEmpty')}
  />

  <SectionBlock
    label="Section F"
    title={$t('section.sleeperPicks')}
    meta={$t('section.sleeperMeta')}
    items={brief.sleeper_picks}
    emptyMessage={$t('section.sleeperEmpty')}
  />
{/if}
