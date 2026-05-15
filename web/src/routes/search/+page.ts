import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ url, fetch }) => {
  const q = url.searchParams.get('q') ?? '';
  if (!q) return { q: '', results: null };
  const results = await apiFetch<{
    query: string;
    researchers: Array<{
      slug: string;
      name_en: string;
      name_zh: string | null;
      current_role: string | null;
      country: string | null;
      confidence_level: string;
      h_index: number | null;
      citation_count: number | null;
      n_papers: number;
      tags: Array<{ label: string }>;
    }>;
    matched_via_tags: Array<{ slug: string; name_en: string; name_zh: string | null }>;
    papers: Array<{ arxiv_id: string | null; title: string; first_seen_at: string | null }>;
  }>(`/search/?q=${encodeURIComponent(q)}`, fetch);
  return { q, results };
};
