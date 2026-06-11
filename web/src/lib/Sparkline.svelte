<script lang="ts">
  // Tiny inline trend line — no axes, no labels, just the shape of the move.
  // Backed by /researchers/{slug}/history snapshots (90-day window). Renders
  // nothing with fewer than 2 points: a single dot is not a trend.

  let { values = [] }: { values: number[] } = $props();

  const W = 120;
  const H = 28;
  const PAD = 2;

  const points = $derived.by(() => {
    if (values.length < 2) return '';
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1; // flat series → centered horizontal line
    const stepX = (W - PAD * 2) / (values.length - 1);
    return values
      .map((v, i) => {
        const x = PAD + i * stepX;
        const y = H - PAD - ((v - min) / span) * (H - PAD * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  });
</script>

{#if points}
  <svg
    width={W}
    height={H}
    viewBox={`0 0 ${W} ${H}`}
    role="img"
    aria-label={`trend, ${values.length} points`}
  >
    <polyline
      {points}
      fill="none"
      stroke="var(--ink)"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
{/if}

<style>
  svg {
    display: block;
    overflow: visible;
  }
</style>
