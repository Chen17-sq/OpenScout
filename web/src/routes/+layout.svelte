<script lang="ts">
  import '../app.css';
  import NavBar from '$lib/NavBar.svelte';

  let { children } = $props();
</script>

<div class="wrap">
  <NavBar />
  {@render children()}
  <footer class="site-footer">
    All the research that's fit to watch · every morning at 09:00 Beijing ·
    <a href="https://github.com/Chen17-sq/OpenScout" target="_blank" rel="noreferrer">GitHub</a>
  </footer>
</div>
