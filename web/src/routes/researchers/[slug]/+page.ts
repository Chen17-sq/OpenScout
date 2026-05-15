import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

type Researcher = {
  slug: string;
  name_en: string;
  name_zh: string | null;
  email: string | null;
  homepage_url: string | null;
  twitter_handle: string | null;
  github_handle: string | null;
  zhihu_url: string | null;
  current_role: string | null;
  career_stage_year: number | null;
  graduation_year_estimate: number | null;
  bio: string | null;
  bio_zh: string | null;
  confidence_level: string;
  current_affiliation: { name: string; name_zh: string | null; country: string | null } | null;
  advisor: { slug: string; name_en: string; name_zh: string | null } | null;
  papers: Array<{
    arxiv_id: string | null;
    title: string;
    abstract: string | null;
    venue: string | null;
    published_at: string | null;
    first_seen_at: string | null;
    position: number;
    topics: string[];
  }>;
};

export const load: PageLoad = async ({ params, fetch }) => {
  const r = await apiFetch<Researcher>(`/researchers/${params.slug}`, fetch);
  if (!r) throw error(404, `researcher ${params.slug} not found`);
  return { researcher: r };
};
