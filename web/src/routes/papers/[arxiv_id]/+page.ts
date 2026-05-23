import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

type Paper = {
  arxiv_id: string | null;
  openalex_id?: string | null;
  title: string;
  abstract: string | null;
  one_liner_zh: string | null;
  published_at: string | null;
  first_seen_at?: string | null;
  venue: string | null;
  pdf_url: string | null;
  code_url: string | null;
  citation_count: number;
  github_stars?: number | null;
  buzz_score?: number | null;
  work_score?: number | null;
  author_emails?: string[] | null;
  authors?: Array<{
    slug: string;
    name_en: string;
    name_zh: string | null;
    position: number;
    current_role: string | null;
    country: string | null;
    h_index: number | null;
    citation_count: number | null;
    confidence_level: string;
  }> | null;
  topics?: Array<{ slug: string; name: string }> | null;
};

export const load: PageLoad = async ({ params, fetch }) => {
  const p = await apiFetch<Paper>(`/papers/${params.arxiv_id}`, fetch);
  if (!p) throw error(404, `paper ${params.arxiv_id} not found`);
  // Defensive defaults — API may omit these collections
  const paper = {
    ...p,
    authors: p.authors ?? [],
    author_emails: p.author_emails ?? [],
    topics: p.topics ?? [],
  };
  return { paper };
};
