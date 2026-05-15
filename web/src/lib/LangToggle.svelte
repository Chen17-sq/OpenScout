<script lang="ts">
  import { locale, t } from './i18n';
</script>

<div class="lang-toggle" role="group" aria-label={$t('langToggle.aria')}>
  <button
    type="button"
    class:active={$locale === 'zh'}
    onclick={() => locale.set('zh')}>中</button
  >
  <button
    type="button"
    class:active={$locale === 'en'}
    onclick={() => locale.set('en')}>EN</button
  >
</div>

<style>
  .lang-toggle {
    display: inline-flex;
    border: 1px solid var(--paper);
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.18em;
  }
  .lang-toggle button {
    background: transparent;
    border: 0;
    color: var(--paper);
    padding: 1px 7px;
    cursor: pointer;
    font: inherit;
    letter-spacing: inherit;
    line-height: 1.6;
  }
  .lang-toggle button.active {
    background: var(--paper);
    color: var(--ink);
  }
  .lang-toggle button + button {
    border-left: 1px solid var(--paper);
  }
</style>
