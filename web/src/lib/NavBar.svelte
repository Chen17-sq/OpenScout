<script lang="ts">
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { locale, t } from './i18n';

  const links = [
    { href: '/', key: 'nav.today' },
    { href: '/researchers', key: 'nav.researchers' },
    { href: '/topics', key: 'nav.topics' },
    { href: '/tags', key: 'nav.tags' },
    { href: '/editions', key: 'nav.archive' },
    { href: '/watchlist', key: 'nav.watchlist' },
    { href: '/stats', key: 'nav.stats' },
  ];

  // Global keyboard shortcut: `/` focuses the search box.
  function onKeydown(e: KeyboardEvent) {
    if (e.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
      e.preventDefault();
      const input = document.querySelector<HTMLInputElement>('.nav-search input');
      input?.focus();
    }
  }

  $effect(() => {
    if (typeof window === 'undefined') return;
    window.addEventListener('keydown', onKeydown);
    return () => window.removeEventListener('keydown', onKeydown);
  });

  const path = $derived(page.url.pathname);
  const isActive = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));

  let q = $state('');

  function onSubmit(e: SubmitEvent) {
    e.preventDefault();
    const term = q.trim();
    if (!term) return;
    goto(`/search?q=${encodeURIComponent(term)}`);
  }
</script>

<div class="nav-shell">
  <nav class="navbar">
    {#each links as link}
      <a href={link.href} class:active={isActive(link.href)}>{$t(link.key)}</a>
    {/each}
  </nav>
  <form class="nav-search" onsubmit={onSubmit} role="search">
    <input
      type="search"
      placeholder={$t('nav.searchPlaceholder')}
      bind:value={q}
      aria-label={$t('nav.search')}
    />
    <button type="submit">⌕</button>
  </form>
  <div class="nav-lang" role="group" aria-label={$t('langToggle.aria')}>
    <button type="button" class:active={$locale === 'zh'} onclick={() => locale.set('zh')}>中</button>
    <button type="button" class:active={$locale === 'en'} onclick={() => locale.set('en')}>EN</button>
  </div>
</div>

<style>
  .nav-shell {
    display: flex;
    align-items: stretch;
    border-bottom: 1px solid var(--ink);
    background: var(--paper);
  }
  .navbar {
    display: flex;
    flex: 1;
  }
  .nav-search {
    display: flex;
    align-items: stretch;
    border-left: 1px solid var(--ink);
  }
  .nav-search input {
    border: 0;
    background: transparent;
    padding: 0 16px;
    width: 220px;
    font-family: 'Lora', serif;
    font-size: 13px;
    color: var(--ink);
    outline: none;
  }
  .nav-search input::placeholder {
    color: var(--n400);
    font-style: italic;
  }
  .nav-search button {
    background: var(--ink);
    color: var(--paper);
    border: 0;
    padding: 0 18px;
    cursor: pointer;
    font-size: 17px;
  }
  .nav-lang {
    display: flex;
    border-left: 1px solid var(--ink);
  }
  .nav-lang button {
    background: var(--paper);
    color: var(--ink);
    border: 0;
    padding: 0 14px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.18em;
  }
  .nav-lang button.active {
    background: var(--ink);
    color: var(--paper);
  }
  .nav-lang button + button {
    border-left: 1px solid var(--ink);
  }
</style>
