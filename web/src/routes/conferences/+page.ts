import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const venues = await apiFetch<Array<{ venue: string; n_papers: number }>>(
    '/conferences/',
    fetch,
  );
  return { venues: venues ?? [] };
};
