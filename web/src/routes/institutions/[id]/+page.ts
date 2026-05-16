import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export const load: PageLoad = async ({ params, fetch }) => {
  const inst = await apiFetch<{
    id: number;
    name: string;
    name_zh: string | null;
    country: string | null;
    type: string | null;
    homepage_url: string | null;
    researchers: Array<{
      slug: string;
      name_en: string;
      name_zh: string | null;
      current_role: string | null;
      h_index: number | null;
      citation_count: number | null;
      tags: Array<{ label: string }>;
    }>;
  }>(`/institutions/${params.id}`, fetch);
  if (!inst) throw error(404, 'institution not found');
  return { inst };
};
