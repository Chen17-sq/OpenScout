<script lang="ts">
  import '../app.css';
  import NavBar from '$lib/NavBar.svelte';
  import { hydrateLocale, t } from '$lib/i18n';

  let { data, children } = $props();

  hydrateLocale(data.locale);
</script>

<div class="wrap">
  <NavBar />
  {@render children()}
  <footer class="site-footer">
    {$t('footer.motto')} ·
    <a href="https://github.com/Chen17-sq/OpenScout" target="_blank" rel="noreferrer">{$t('footer.github')}</a>
  </footer>
</div>
