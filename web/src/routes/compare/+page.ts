import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

type R = {
  slug: string;
  name_en: string;
  name_zh: string | null;
  current_role: string | null;
  country: string | null;
  h_index: number | null;
  citation_count: number | null;
  works_count: number | null;
  confidence_level: string;
  bio: string | null;
  tags: Array<{ label: string; score: number }>;
  projects: Array<{ name: string; role?: string; category?: string; url?: string }>;
  current_affiliation: { name: string; name_zh: string | null } | null;
  signature_paper: { arxiv_id: string | null; title: string; citation_count: number } | null;
  person_score: number | null;
  trajectory_score: number | null;
  investability_score: number | null;
};

export const load: PageLoad = async ({ url, fetch }) => {
  const a = url.searchParams.get('a');
  const b = url.searchParams.get('b');
  if (!a || !b) return { a: null, b: null };
  const [ra, rb] = await Promise.all([
    apiFetch<R>(`/researchers/${a}`, fetch),
    apiFetch<R>(`/researchers/${b}`, fetch),
  ]);
  return { a: ra, b: rb };
};
