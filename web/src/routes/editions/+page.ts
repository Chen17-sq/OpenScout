import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const briefs = await apiFetch<
    Array<{ brief_date: string; volume: number; issue: number; generated_at: string | null }>
  >('/briefs/list?limit=60', fetch);
  return { briefs: briefs ?? [] };
};
