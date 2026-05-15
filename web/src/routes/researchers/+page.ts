import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ url, fetch }) => {
  const params = new URLSearchParams();
  for (const k of ['stage', 'confidence', 'topic', 'q']) {
    const v = url.searchParams.get(k);
    if (v) params.set(k, v);
  }
  params.set('limit', '100');
  const data = await apiFetch<{
    total: number;
    items: Array<{
      slug: string;
      name_en: string;
      name_zh: string | null;
      current_role: string | null;
      confidence_level: string;
      n_papers: number;
      bio: string | null;
    }>;
  }>(`/researchers/?${params.toString()}`, fetch);
  return {
    data,
    filters: {
      stage: url.searchParams.get('stage') ?? '',
      confidence: url.searchParams.get('confidence') ?? '',
      topic: url.searchParams.get('topic') ?? '',
      q: url.searchParams.get('q') ?? '',
    },
  };
};
