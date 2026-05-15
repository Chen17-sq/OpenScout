import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const [overview, topCollab, byTopic] = await Promise.all([
    apiFetch<{
      totals: { researchers: number; anchors: number; papers: number; topics: number };
      series_7d: Array<{ date: string; papers: number; researchers: number }>;
    }>('/stats/', fetch),
    apiFetch<
      Array<{
        slug: string;
        name_en: string;
        name_zh: string | null;
        current_role: string | null;
        confidence_level: string;
        n_papers: number;
      }>
    >('/stats/top-collaborators?limit=20', fetch),
    apiFetch<Array<{ slug: string; name: string; name_zh: string | null; n_papers: number }>>(
      '/stats/by-topic',
      fetch,
    ),
  ]);
  return { overview, topCollab: topCollab ?? [], byTopic: byTopic ?? [] };
};
