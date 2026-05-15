<script lang="ts">
  import { page } from '$app/state';

  const links = [
    { href: '/', label: 'Today' },
    { href: '/researchers', label: 'Researchers' },
    { href: '/topics', label: 'Topics' },
    { href: '/editions', label: 'Archive' },
    { href: '/stats', label: 'Stats' },
  ];

  const path = $derived(page.url.pathname);
  const isActive = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));
</script>

<nav class="navbar">
  {#each links as link}
    <a href={link.href} class:active={isActive(link.href)}>{link.label}</a>
  {/each}
</nav>
