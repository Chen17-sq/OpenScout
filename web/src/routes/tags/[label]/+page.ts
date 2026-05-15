import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ params, fetch }) => {
  const label = decodeURIComponent(params.label);
  const researchers = await apiFetch<
    Array<{
      slug: string;
      name_en: string;
      name_zh: string | null;
      current_role: string | null;
      country: string | null;
      confidence_level: string;
      h_index: number | null;
      citation_count: number | null;
    }>
  >(`/tags/${encodeURIComponent(label)}?limit=50`, fetch);
  return { label, researchers: researchers ?? [] };
};
