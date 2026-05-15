import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const tags = await apiFetch<
    Array<{ label: string; count: number; avg_score: number; level: number }>
  >('/tags/?limit=80&min_count=2', fetch);
  return { tags: tags ?? [] };
};
