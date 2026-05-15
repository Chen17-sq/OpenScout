# OpenScout

> *All The Researchers Fit To Watch.*
> 一份每日发行的报纸 — 早期发现具身智能 / 世界模型 / AI for Science 的高潜研究者。

OpenScout 每天从 arXiv、Semantic Scholar、实验室主页、社交信号里挖出值得 cover 的年轻 researcher——PhD 毕业季、即将入职 AP、知名教授的徒子徒孙——并以编辑部式的日报形式呈现。

- 每个 researcher：profile + 发表时间线 + 师承脉络 + 近期信号 + 联系方式
- 每一天：Section A 头版概览 / B 今日新冒头 / C 即将毕业 / D 即将入职 AP / E 热门工作 / F Sleeper Picks

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | SvelteKit 2 · Svelte 5 · Tailwind 4 |
| Backend | FastAPI · SQLAlchemy 2 · Pydantic 2 |
| DB | Postgres 16 + pgvector |
| Scraper | `arxiv` · `semanticscholar` · `playwright` · `httpx` |
| LLM | Claude Haiku 4.5（主题分类 / 中文一句话） |
| Cron | GitHub Actions → POST `/admin/ingest` |
| Email | Resend |

## Quick start

```bash
# 1. Postgres + pgvector
docker compose up -d postgres

# 2. Backend
uv sync
uv run openscout init-db
uv run openscout seed
uv run openscout ingest --topic embodied --limit 50

# 3. Frontend
cd web && npm install && npm run dev
```

## Repo layout

```
src/openscout/
  api/          FastAPI app + routes
  scraper/      arxiv / semanticscholar / homepage / classify
  brief/        daily brief generator + markdown export
  models.py     SQLAlchemy schema
  config.py     pydantic-settings
  cli.py        typer CLI

web/            SvelteKit frontend

seeds/
  topics.yaml         3 个领域 + 子主题
  advisors.yaml       种子导师（PhD 树的 root）
  researchers.yaml    手工 curate 的高潜池

.github/workflows/
  ingest.yml          每日 cron → /admin/ingest
  deploy.yml          前后端部署
```

## Design notes

OpenScout 的日报排版语言取自姊妹项目 [kickstarter-china-tracker](https://github.com/Chen17-sq/kickstarter-china-tracker)（NYT pastiche · Newsprint masthead · ✦ 分隔 · Section A-F · Sleeper Picks 算法栏）。后端是真正的 web app 而非静态站，因为研究者数据是关系型的（作者-论文-机构-师承），需要查询和聚合而不是文件读取。

## License

[MIT](LICENSE)
