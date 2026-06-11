<script lang="ts">
  import '../app.css';
  import NavBar from '$lib/NavBar.svelte';
  import { API_BASE } from '$lib/api';
  import { hydrateLocale, t } from '$lib/i18n';

  let { data, children } = $props();

  // Hydrate locale on every navigation (data is reactive in Svelte 5 runes mode).
  $effect(() => {
    hydrateLocale(data.locale);
  });
</script>

<div class="wrap">
  <NavBar />
  {@render children()}
  <footer class="site-footer">
    <div>{$t('footer.motto')}</div>
    <div class="footer-links">
      <a href="{API_BASE}/rss/daily" target="_blank" rel="noreferrer">📡 {$t('footer.rss')}</a>
      <span class="sep">·</span>
      <a href="https://github.com/Chen17-sq/OpenScout" target="_blank" rel="noreferrer"
        >{$t('footer.github')}</a
      >
      <span class="sep">·</span>
      <a href="https://github.com/Chen17-sq/OpenScout/tree/data" target="_blank" rel="noreferrer"
        >{$t('footer.dataSnapshot')}</a
      >
      <span class="sep">·</span>
      <a href="/about">{$t('footer.about')}</a>
    </div>
  </footer>
</div>

<style>
  .footer-links {
    margin-top: 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--n500);
  }
  .footer-links a {
    color: var(--n500);
    font-weight: 500;
    text-decoration: none;
  }
  .footer-links a:hover {
    color: var(--ink);
    text-decoration: underline;
  }
  .footer-links .sep {
    margin: 0 6px;
    color: var(--n400);
  }
</style>
