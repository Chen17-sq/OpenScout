<script lang="ts">
  import EditionStrip from '$lib/EditionStrip.svelte';
  import Masthead from '$lib/Masthead.svelte';
  import KpiBand from '$lib/KpiBand.svelte';
  import HeroSection from '$lib/HeroSection.svelte';
  import SectionBlock from '$lib/SectionBlock.svelte';

  let { data } = $props();
  const brief = $derived(data.brief);
</script>

{#if !brief}
  <Masthead />
  <div class="story-card">
    <div></div>
    <div>
      <div class="title">Backend offline</div>
      <div class="blurb">API at http://localhost:8000 unreachable. Start it: <code>make api</code></div>
    </div>
    <div></div>
  </div>
{:else}
  <EditionStrip issue={brief.issue} briefDate={brief.brief_date} />
  <Masthead briefDate={brief.brief_date} issue={brief.issue} />

  <KpiBand kpi={brief.kpi} />

  <HeroSection
    leftLabel="🆕 今日新冒头"
    leftMeta="first-authors first seen today"
    rightLabel="🔄 动态更新 (anchor activity)"
    rightMeta="known faces shipping today"
    leftItems={brief.new_first_authors}
    rightItems={brief.anchor_activity}
    rightAccent
  />

  <SectionBlock
    label="Section C"
    title="🎓 即将毕业 PhD"
    meta="v0 fallback: 最高产 first-author"
    items={brief.soon_graduating_picks}
    emptyMessage="_数据不足 — 需要 career_stage_year 推断 (TODO)._"
  />

  <SectionBlock
    label="Section E"
    title="🔥 热门工作"
    meta="ranked by collaboration weight"
    items={brief.hot_papers}
    emptyMessage="_今日无新 paper_"
  />

  <SectionBlock
    label="Section F"
    title="🌙 Sleeper Picks"
    meta="algorithmic — 写明被选中的原因"
    items={brief.sleeper_picks}
    emptyMessage="_今日无符合算法的候选 — 算法看上去保守了_"
  />
{/if}
