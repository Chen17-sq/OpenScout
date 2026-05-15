<script lang="ts">
  let { issue = 1, briefDate = '' }: { issue?: number; briefDate?: string } = $props();

  const weekday = $derived(
    briefDate ? new Date(briefDate + 'T00:00:00Z').toLocaleDateString('en-US', { weekday: 'long', timeZone: 'UTC' }).toUpperCase() : '',
  );
</script>

<div class="edition-strip">
  <span><span class="live-dot"></span>LIVE EDITION</span>
  <span>VOL. 1 · NO. {String(issue).padStart(3, '0')}{weekday ? ` · ${weekday}` : ''}</span>
  <span>BEIJING / GLOBAL</span>
</div>
