<script lang="ts">
  import type { BriefData } from './api';

  let { kpi }: { kpi: BriefData['kpi'] } = $props();
</script>

<div class="kpi-row">
  <div class="kpi">
    <div class="label">Tracked</div>
    <div class="num">{kpi.tracked.toLocaleString()}</div>
    <div class="delta">all researchers</div>
  </div>
  <div class="kpi is-accent">
    <div class="label">今日新增 paper</div>
    <div class="num">{kpi.today_papers.toLocaleString()}</div>
    <div class="delta">across 3 topics</div>
  </div>
  <div class="kpi is-accent">
    <div class="label">新冒头</div>
    <div class="num">{kpi.today_emergences.toLocaleString()}</div>
    <div class="delta">first-seen today</div>
  </div>
  <div class="kpi">
    <div class="label">毕业季 PhD</div>
    <div class="num">{kpi.soon_graduating.toLocaleString()}</div>
    <div class="delta">PhD-Y4/Y5</div>
  </div>
  <div class="kpi">
    <div class="label">即将入职 AP</div>
    <div class="num">{kpi.incoming_ap.toLocaleString()}</div>
    <div class="delta">offers announced</div>
  </div>
</div>
