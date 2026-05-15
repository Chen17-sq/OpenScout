<script lang="ts">
  import { t } from '$lib/i18n';
</script>

<section>
  <div class="section-head">
    <div class="label">Subscribe</div>
    <div class="h">Daily Email Digest</div>
    <div class="meta">delivered 09:00 Beijing</div>
  </div>

  <div class="sub-wrap">
    <p class="intro">
      OpenScout 每天 09:00 北京时间生成一份新日报。三种订阅方式：
    </p>

    <article class="opt">
      <h3>📧 邮件</h3>
      <p>
        把每日 brief 推到你的邮箱。运行后端的人需要在 <code>.env</code> 里配
        <code>RESEND_API_KEY</code> 和 <code>NOTIFY_EMAIL_TO</code>，然后 cron 自动
        发送（<code>openscout send-digest</code>）。
      </p>
    </article>

    <article class="opt">
      <h3>📡 RSS</h3>
      <p>
        把以下任一 URL 加到你的 feed reader（NetNewsWire / Reeder / Inoreader）：
      </p>
      <ul>
        <li><code><a href="/rss/daily" target="_blank">/rss/daily</a></code> — 完整日报 permalink</li>
        <li><code><a href="/rss/papers" target="_blank">/rss/papers</a></code> — 最近 50 篇 paper</li>
      </ul>
    </article>

    <article class="opt">
      <h3>⭐ Watchlist</h3>
      <p>
        在任意 <a href="/researchers">研究者</a> 详情页点 ★ 把人加进
        <a href="/watchlist">收藏</a>。本地浏览器存储，不需要登录。
      </p>
    </article>

    <article class="opt">
      <h3>🐦 社交分享</h3>
      <p>
        每天自动生成 9 张 SVG 卡片，<a href="/static/social">在这里看</a>。
        小红书 / 朋友圈 9 图直接拖去用。
      </p>
    </article>
  </div>
</section>

<style>
  .sub-wrap {
    padding: 30px 28px 60px;
    max-width: 740px;
  }
  .intro {
    font-family: 'Lora', serif;
    font-style: italic;
    color: var(--n700);
    font-size: 17px;
    margin-bottom: 32px;
  }
  .opt {
    padding: 18px 0;
    border-top: 1px solid var(--muted);
  }
  .opt h3 {
    font-family: 'Playfair Display', serif;
    font-weight: 700;
    font-size: 22px;
    margin: 0 0 6px;
  }
  .opt p,
  .opt li {
    font-family: 'Lora', serif;
    font-size: 14px;
    line-height: 1.6;
    color: var(--n700);
  }
  .opt code {
    background: var(--n100);
    padding: 1px 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
  }
  .opt a {
    color: var(--ink);
    text-decoration: underline;
    text-decoration-color: var(--n400);
  }
  .opt a:hover {
    color: var(--accent);
  }
</style>
