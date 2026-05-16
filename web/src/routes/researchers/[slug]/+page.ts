import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

type Tag = { label: string; score: number; level?: number; wikidata?: string };
type Project = { name: string; role?: string; category?: string; url?: string };
type PaperRow = {
  arxiv_id: string | null;
  title: string;
  abstract: string | null;
  venue: string | null;
  published_at: string | null;
  first_seen_at: string | null;
  position: number;
  topics: string[];
  citation_count?: number;
  author_emails?: string[];
};

type Researcher = {
  slug: string;
  name_en: string;
  name_zh: string | null;
  name_zh_source: string | null;
  email: string | null;
  homepage_url: string | null;
  twitter_handle: string | null;
  github_handle: string | null;
  zhihu_url: string | null;
  linkedin_url: string | null;
  photo_url: string | null;
  current_role: string | null;
  career_stage_year: number | null;
  graduation_year_estimate: number | null;
  country: string | null;
  // Provenance of inferred fields — see SourceBadge.svelte
  country_source: string | null;
  role_source: string | null;
  affiliation_source: string | null;
  investability_score_v2: number | null;
  // Deep-dive freshness — null until the first dive
  deep_dive_run_at: string | null;
  deep_dive_sources_used: Record<string, string>;
  bio: string | null;
  bio_zh: string | null;
  confidence_level: string;
  openalex_id: string | null;
  orcid: string | null;
  h_index: number | null;
  citation_count: number | null;
  works_count: number | null;
  tags: Tag[];
  projects: Project[];
  current_affiliation: { name: string; name_zh: string | null; country: string | null } | null;
  advisor: { slug: string; name_en: string; name_zh: string | null } | null;
  inferred_advisors: Array<{
    slug: string;
    name_en: string;
    name_zh: string | null;
    confidence: string;
    evidence: string | null;
  }>;
  students: Array<{
    slug: string;
    name_en: string;
    name_zh: string | null;
    current_role: string | null;
    h_index: number | null;
  }>;
  signature_paper: {
    arxiv_id: string | null;
    title: string;
    abstract: string | null;
    citation_count: number;
    topics: string[];
  } | null;
  papers: PaperRow[];
};

export const load: PageLoad = async ({ params, fetch }) => {
  const r = await apiFetch<Researcher>(`/researchers/${params.slug}`, fetch);
  if (!r) throw error(404, `researcher ${params.slug} not found`);
  return { researcher: r };
};
