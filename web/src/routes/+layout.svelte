<script lang="ts">
  import '../app.css';

  let { children } = $props();
</script>

<main class="mx-auto max-w-5xl px-6 py-10">
  {@render children()}
</main>
