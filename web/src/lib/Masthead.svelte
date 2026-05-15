<script lang="ts">
  import { locale, t } from './i18n';

  let {
    briefDate = '',
    issue = 1,
  }: { briefDate?: string; issue?: number } = $props();

  const pretty = $derived(
    briefDate
      ? new Date(briefDate + 'T00:00:00Z').toLocaleDateString(
          $locale === 'zh' ? 'zh-CN' : 'en-US',
          {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            timeZone: 'UTC',
          },
        )
      : '',
  );
</script>

<header class="mast">
  <h1 class="nameplate">OpenScout</h1>

  <div class="mast-tag">
    <span>VOL. 1 · NO. {String(issue).padStart(3, '0')}</span>
    <span class="center">{$t('masthead.tagline')}</span>
    <span>{pretty ? pretty.toUpperCase() : $t('masthead.daily')}</span>
  </div>

  <p class="dek">{$t('masthead.dek')}</p>
</header>
