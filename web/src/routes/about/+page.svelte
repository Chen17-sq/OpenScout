<script lang="ts">
  import { t } from '$lib/i18n';
</script>

<section>
  <div class="section-head">
    <div class="label">About</div>
    <div class="h">OpenScout</div>
    <div class="meta">All The Researchers Fit To Watch.</div>
  </div>

  <div class="about-body">
    <p class="lead">
      OpenScout 是一份每日发行的报纸 — 早期发现 具身智能 · 世界模型 · AI for Science
      中的高潜研究者。从 arXiv、OpenAlex、HuggingFace、OpenReview、实验室主页、
      社交信号里反向 mapping。
    </p>

    <h3>为什么做这个</h3>
    <p>
      投资人 cover 学者最大的难题是 "怎么早点看到值得 cover 的人"。
      当一篇工作上 alphaxiv 头条、媒体开始报道时，已经晚了。
      OpenScout 的目标：从 paper 反向 mapping 到 author，再把脉络（advisor /
      lab / 同期 cohort）补全，让你提前几个月看到苗头。
    </p>

    <h3>数据来源</h3>
    <ul>
      <li><strong>arXiv</strong> — 每日新 paper（cs.RO / cs.LG / cs.AI / cs.CV）</li>
      <li><strong>OpenAlex</strong> — citation / h-index / topic tags / 中文名
        (display_name_alternatives) — 免费、无 rate limit</li>
      <li><strong>OpenReview</strong> — ICLR / NeurIPS / ICML 接收论文 (含 oral/spotlight)</li>
      <li><strong>HuggingFace</strong> — Daily Papers + 模型发布信号</li>
      <li><strong>arXiv PDF</strong> — pypdf 提取首页脚注里的邮箱</li>
      <li><strong>Wikidata</strong> — 部分 anchor 的照片 (P18)</li>
      <li><strong>种子 YAML</strong> — 50+ 手工挑的 anchor researchers + 机构 + 旗舰项目</li>
    </ul>

    <h3>设计原则</h3>
    <ul>
      <li><strong>不靠猜</strong> — Chinese name 只在能验证的来源出现时才写</li>
      <li><strong>报纸视觉</strong> — 取自 NYT 排版语言，Playfair / Lora / Inter / JetBrains Mono</li>
      <li><strong>多消费面</strong> — Web / RSS / Markdown / 9 图 / 邮件 (Resend)</li>
      <li><strong>本地优先</strong> — 默认 SQLite，Postgres 留给 prod</li>
    </ul>

    <h3>致谢</h3>
    <p>
      架构借鉴自姊妹项目 <a href="https://github.com/Chen17-sq/kickstarter-china-tracker" target="_blank" rel="noreferrer">kickstarter-china-tracker</a>
      (每日报纸 + GitHub Actions cron + JSON commits)。
      开源组件: <code>pyalex</code> · <code>pypdf</code> · <code>feedgen</code> ·
      <code>SvelteKit</code> · <code>Tailwind</code> · <code>marked</code>.
    </p>

    <h3>源码 & License</h3>
    <p>
      <a href="https://github.com/Chen17-sq/OpenScout" target="_blank" rel="noreferrer">github.com/Chen17-sq/OpenScout</a> · MIT
    </p>
  </div>
</section>

<style>
  .about-body {
    padding: 30px 28px 60px;
    max-width: 720px;
    font-family: 'Lora', serif;
    font-size: 16px;
    line-height: 1.7;
    color: var(--n700);
  }
  .about-body .lead {
    font-size: 19px;
    font-style: italic;
    margin: 0 0 30px;
    color: var(--ink);
  }
  .about-body h3 {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 24px;
    margin: 32px 0 10px;
    letter-spacing: -0.5px;
    color: var(--ink);
  }
  .about-body ul {
    padding-left: 22px;
  }
  .about-body li {
    margin: 6px 0;
  }
  .about-body code {
    background: var(--n100);
    padding: 1px 5px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
  }
  .about-body a {
    color: var(--ink);
    text-decoration: underline;
    text-decoration-color: var(--n400);
  }
  .about-body a:hover {
    color: var(--accent);
  }
</style>
