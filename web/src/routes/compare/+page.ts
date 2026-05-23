import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

// One researcher row — only the fields the compare grid renders.
type R = {
  slug: string;
  name_en: string;
  name_zh: string | null;
  current_role: string | null;
  country: string | null;
  photo_url: string | null;
  h_index: number | null;
  citation_count: number | null;
  works_count: number | null;
  confidence_level: string;
  bio: string | null;
  tags: Array<{ label: string; label_zh?: string | null; score?: number; type?: string }>;
  projects: Array<{ name: string; role?: string; category?: string; url?: string }>;
  current_affiliation: { name: string; name_zh: string | null } | null;
  signature_paper: {
    arxiv_id: string | null;
    title: string;
    citation_count: number;
  } | null;
  papers: Array<{
    arxiv_id: string | null;
    title: string;
    position: number;
    citation_count?: number;
    venue: string | null;
    published_at: string | null;
  }>;
  person_score: number | null;
  trajectory_score: number | null;
  investability_score: number | null;
  investability_score_v2: number | null;
};

// Accepts the new `slugs=a,b,c` (preferred) and the legacy `a=…&b=…`.
// Keeping both lets old shared URLs keep working.
function parseSlugs(url: URL): string[] {
  const sl = url.searchParams.get('slugs');
  if (sl) {
    return sl
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 3);
  }
  const legacy = [url.searchParams.get('a'), url.searchParams.get('b'), url.searchParams.get('c')]
    .filter((x): x is string => !!x)
    .slice(0, 3);
  return legacy;
}

export const load: PageLoad = async ({ url, fetch }) => {
  const slugs = parseSlugs(url);
  if (slugs.length === 0) return { slugs, researchers: [] as R[] };
  const results = await Promise.all(
    slugs.map((s) => apiFetch<R>(`/researchers/${s}`, fetch)),
  );
  // keep slugs in order, drop nulls (404s)
  const researchers = results.filter((x): x is R => !!x);
  return { slugs, researchers };
};
