<script lang="ts">
  let {
    briefDate = '',
    issue = 1,
  }: { briefDate?: string; issue?: number } = $props();

  const pretty = $derived(
    briefDate
      ? new Date(briefDate + 'T00:00:00Z').toLocaleDateString('en-US', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
          timeZone: 'UTC',
        })
      : '',
  );
</script>

<header class="mast">
  <h1 class="nameplate">OpenScout</h1>

  <div class="mast-tag">
    <span>VOL. 1 · NO. {String(issue).padStart(3, '0')}</span>
    <span class="center">"All The Researchers Fit To Watch."</span>
    <span>{pretty ? pretty.toUpperCase() : 'DAILY'}</span>
  </div>

  <p class="dek">
    一份每日发行的报纸 — 早期发现 具身智能 · 世界模型 · AI for Science 中的高潜研究者。
    从 arXiv、Semantic Scholar、实验室主页、社交信号里反向 mapping。
  </p>
</header>
