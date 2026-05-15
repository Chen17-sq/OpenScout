import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const topics = await apiFetch<
    Array<{ slug: string; name: string; name_zh: string | null; description: string | null; n_papers: number }>
  >('/topics/', fetch);
  return { topics: topics ?? [] };
};
