import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export type PaperListItem = {
  arxiv_id: string | null;
  title: string;
  published_at: string | null;
  venue: string | null;
  citation_count: number;
  github_stars: number | null;
  work_score: number | null;
  breakthrough_score: number | null;
  commercial_score: number | null;
  buzz_score: number | null;
  topics: string[];
  n_authors: number;
};

type ListResponse = {
  total: number;
  limit: number;
  offset: number;
  items: PaperListItem[];
};

export const load: PageLoad = async ({ url, fetch }) => {
  const params = new URLSearchParams();
  for (const k of ['topic', 'has_code', 'sort']) {
    const v = url.searchParams.get(k);
    if (v) params.set(k, v);
  }
  const limit = 50;
  const offset = parseInt(url.searchParams.get('offset') ?? '0', 10) || 0;
  params.set('limit', String(limit));
  params.set('offset', String(offset));

  const data = await apiFetch<ListResponse>(`/papers/?${params.toString()}`, fetch);
  return {
    data,
    filters: {
      topic: url.searchParams.get('topic') ?? '',
      has_code: url.searchParams.get('has_code') ?? '',
      sort: url.searchParams.get('sort') ?? '',
    },
  };
};
