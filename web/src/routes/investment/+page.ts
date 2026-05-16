// /investment — full Investment Lens browser.
//
// We fetch:
//   1) /investment/picks at the largest allowed limit (50) for the chosen
//      time window — the API itself does the heavy three-pillar ranking.
//   2) /researchers/?limit=200 — purely as a side-lookup for `bio` + `tags`
//      (the picks endpoint doesn't return those, but the row table wants
//      to show a truncated bio and the topic-search needs `tag.label`).
//
// All filters/sort/pagination/search happen client-side from these two
// fetches. Server-side filtering can be added later without breaking this
// page's contract.

import type { PageLoad } from './$types';
import { apiFetch, type InvestmentPicks } from '$lib/api';

export type ResearcherMeta = {
  slug: string;
  bio: string | null;
  tags: Array<{ label: string; score?: number }>;
};

type ResearcherListItem = {
  slug: string;
  bio?: string | null;
  tags?: Array<{ label: string; score?: number }>;
};
type ResearcherListResponse = { items: ResearcherListItem[] };

export const load: PageLoad = async ({ url, fetch }) => {
  const window_days = parseInt(url.searchParams.get('window') ?? '30', 10) || 30;

  // Fetch picks + researcher metadata in parallel.
  const [picks, roster] = await Promise.all([
    apiFetch<InvestmentPicks>(
      `/investment/picks?limit=50&window_days=${window_days}&max_per_paper=2`,
      fetch,
    ),
    apiFetch<ResearcherListResponse>('/researchers/?limit=200', fetch),
  ]);

  // Build slug -> { bio, tags } map for fast client-side enrichment.
  const metaBySlug: Record<string, ResearcherMeta> = {};
  for (const r of roster?.items ?? []) {
    metaBySlug[r.slug] = {
      slug: r.slug,
      bio: r.bio ?? null,
      tags: r.tags ?? [],
    };
  }

  return {
    picks,
    metaBySlug,
    initialWindow: window_days,
  };
};
