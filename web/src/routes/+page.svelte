<script lang="ts">
  // v0 placeholder homepage. Will fetch /briefs/latest + /researchers from the API.
</script>

<header class="rule-bottom pb-4 mb-10">
  <p class="font-mono text-[11px] tracking-[0.2em] uppercase">
    VOL. 1 · NO. 001 &nbsp;·&nbsp; BEIJING EDITION
  </p>
  <h1 class="masthead text-6xl md:text-7xl font-bold mt-2">OpenScout</h1>
  <p class="mt-2 italic text-base">All The Researchers Fit To Watch.</p>
  <p class="mt-1 text-sm text-stone-600">
    一份每日发行的报纸 — 具身智能 / 世界模型 / AI for Science 的高潜研究者追踪。
  </p>
</header>

<section class="prose max-w-none">
  <h2 class="masthead text-2xl font-semibold">Section A · 头版概览</h2>
  <p class="text-stone-700">
    后端尚未启动。Quick start：
  </p>
  <pre class="bg-stone-100 p-4 rounded text-sm font-mono">
make db-up
make install
make init
make seed
make ingest TOPIC=embodied LIMIT=50
make brief
make dev
  </pre>

  <p class="text-stone-700 mt-6">
    跑完后访问 <code>http://localhost:8000/briefs/latest</code>，或继续完善这个页面来渲染日报。
  </p>
</section>

<footer class="mt-16 pt-6 rule-top text-xs text-stone-500 font-mono">
  All the research that's fit to watch, every morning at 09:00 Beijing.
</footer>
