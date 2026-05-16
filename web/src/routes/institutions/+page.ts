import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const items = await apiFetch<
    Array<{
      id: number;
      name: string;
      name_zh: string | null;
      country: string | null;
      type: string | null;
      n_researchers: number;
      total_citations: number;
    }>
  >('/institutions/', fetch);
  return { items: items ?? [] };
};
