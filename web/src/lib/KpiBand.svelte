<script lang="ts">
  import { t } from './i18n';
  import type { BriefData } from './api';

  let { kpi }: { kpi: BriefData['kpi'] } = $props();
</script>

<div class="kpi-row">
  <div class="kpi">
    <div class="label">{$t('kpi.tracked')}</div>
    <div class="num">{kpi.tracked.toLocaleString()}</div>
    <div class="delta">{$t('kpi.trackedDelta')}</div>
  </div>
  <div class="kpi is-accent">
    <div class="label">{$t('kpi.todayPapers')}</div>
    <div class="num">{kpi.today_papers.toLocaleString()}</div>
    <div class="delta">{$t('kpi.todayPapersDelta')}</div>
  </div>
  <div class="kpi is-accent">
    <div class="label">{$t('kpi.todayEmergences')}</div>
    <div class="num">{kpi.today_emergences.toLocaleString()}</div>
    <div class="delta">{$t('kpi.todayEmergencesDelta')}</div>
  </div>
  <div class="kpi">
    <div class="label">{$t('kpi.soonGraduating')}</div>
    <div class="num">{kpi.soon_graduating.toLocaleString()}</div>
    <div class="delta">{$t('kpi.soonGraduatingDelta')}</div>
  </div>
  <div class="kpi">
    <div class="label">{$t('kpi.incomingAp')}</div>
    <div class="num">{kpi.incoming_ap.toLocaleString()}</div>
    <div class="delta">{$t('kpi.incomingApDelta')}</div>
  </div>
</div>
