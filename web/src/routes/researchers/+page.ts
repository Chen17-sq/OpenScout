import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ url, fetch }) => {
  const params = new URLSearchParams();
  for (const k of ['stage', 'confidence', 'topic', 'country', 'q', 'sort']) {
    const v = url.searchParams.get(k);
    if (v) params.set(k, v);
  }
  const limit = 100;
  const offset = parseInt(url.searchParams.get('offset') ?? '0', 10) || 0;
  params.set('limit', String(limit));
  params.set('offset', String(offset));

  type ListItem = {
    slug: string;
    name_en: string;
    name_zh: string | null;
    current_role: string | null;
    country: string | null;
    confidence_level: string;
    h_index: number | null;
    citation_count: number | null;
    n_papers: number;
    tags: Array<{ label: string; score?: number }>;
  };

  const data = await apiFetch<{ total: number; items: ListItem[] }>(
    `/researchers/?${params.toString()}`,
    fetch,
  );
  return {
    data,
    filters: {
      stage: url.searchParams.get('stage') ?? '',
      confidence: url.searchParams.get('confidence') ?? '',
      topic: url.searchParams.get('topic') ?? '',
      country: url.searchParams.get('country') ?? '',
      sort: url.searchParams.get('sort') ?? '',
      q: url.searchParams.get('q') ?? '',
    },
  };
};
