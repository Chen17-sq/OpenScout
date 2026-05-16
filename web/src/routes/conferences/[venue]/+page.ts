import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ params, fetch }) => {
  const venue = decodeURIComponent(params.venue);
  const prefix = venue.split(/\s+/).slice(0, 2).join(' ');
  const data = await apiFetch<{
    prefix: string;
    n: number;
    papers: Array<{
      arxiv_id: string | null;
      title: string;
      abstract: string | null;
      venue: string | null;
      first_seen_at: string | null;
      buzz_score: number | null;
      first_author: { slug: string; name_en: string; name_zh: string | null } | null;
    }>;
  }>(`/conferences/by-prefix/${encodeURIComponent(prefix)}`, fetch);
  return { data, prefix };
};
