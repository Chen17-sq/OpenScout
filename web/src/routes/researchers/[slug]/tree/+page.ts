import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

type R = {
  slug: string;
  name_en: string;
  name_zh: string | null;
  current_role: string | null;
  citation_count: number | null;
  h_index: number | null;
  advisor: { slug: string; name_en: string; name_zh: string | null } | null;
  inferred_advisors: Array<{
    slug: string;
    name_en: string;
    name_zh: string | null;
    confidence: string;
    evidence: string | null;
  }>;
  students: Array<{ slug: string; name_en: string; name_zh: string | null; current_role: string | null; h_index: number | null }>;
};

export const load: PageLoad = async ({ params, fetch }) => {
  const r = await apiFetch<R>(`/researchers/${params.slug}`, fetch);
  if (!r) throw error(404, `researcher ${params.slug} not found`);
  return { researcher: r };
};
