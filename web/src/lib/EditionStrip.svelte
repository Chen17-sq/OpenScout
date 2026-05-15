<script lang="ts">
  import { locale, t } from './i18n';
  import LangToggle from './LangToggle.svelte';

  let { issue = 1, briefDate = '' }: { issue?: number; briefDate?: string } = $props();

  const weekday = $derived(
    briefDate
      ? new Date(briefDate + 'T00:00:00Z')
          .toLocaleDateString($locale === 'zh' ? 'zh-CN' : 'en-US', {
            weekday: 'long',
            timeZone: 'UTC',
          })
          .toUpperCase()
      : '',
  );
</script>

<div class="edition-strip">
  <span><span class="live-dot"></span>{$t('edition.live')}</span>
  <span>VOL. 1 · NO. {String(issue).padStart(3, '0')}{weekday ? ` · ${weekday}` : ''}</span>
  <span class="strip-right">
    <span>{$t('edition.locale')}</span>
    <LangToggle />
  </span>
</div>

<style>
  .strip-right {
    display: inline-flex;
    align-items: center;
    gap: 14px;
  }
</style>
