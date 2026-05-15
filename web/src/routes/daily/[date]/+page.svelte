<script lang="ts">
  import EditionStrip from '$lib/EditionStrip.svelte';
  import Masthead from '$lib/Masthead.svelte';
  import KpiBand from '$lib/KpiBand.svelte';
  import HeroSection from '$lib/HeroSection.svelte';
  import SectionBlock from '$lib/SectionBlock.svelte';

  let { data } = $props();
  const brief = $derived(data.brief);
</script>

<EditionStrip issue={brief.issue} briefDate={brief.brief_date} />
<Masthead briefDate={brief.brief_date} issue={brief.issue} />
<KpiBand kpi={brief.kpi} />
<HeroSection
  leftLabel="🆕 今日新冒头"
  leftMeta="first-authors first seen this issue"
  rightLabel="🔄 动态更新"
  rightMeta="anchor activity"
  leftItems={brief.new_first_authors}
  rightItems={brief.anchor_activity}
  rightAccent
/>
<SectionBlock
  label="Section C"
  title="🎓 即将毕业 PhD"
  items={brief.soon_graduating_picks}
  emptyMessage="_no data for this date_"
/>
<SectionBlock
  label="Section D"
  title="🚀 即将入职 AP"
  items={brief.incoming_ap_picks}
  emptyMessage="_no incoming AP marked_"
/>
<SectionBlock
  label="Section E"
  title="🔥 热门工作"
  items={brief.hot_papers}
  emptyMessage="_no papers this date_"
/>
<SectionBlock
  label="Section F"
  title="🌙 Sleeper Picks"
  items={brief.sleeper_picks}
  emptyMessage="_no sleeper picks this date_"
/>
