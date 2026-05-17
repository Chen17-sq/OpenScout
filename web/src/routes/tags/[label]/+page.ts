import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export type TagResearcher = {
  slug: string;
  name_en: string;
  name_zh?: string | null;
  country?: string | null;
  current_role?: string | null;
  h_index?: number | null;
  investability_score_v2?: number | null;
};

export type TagDetail = {
  label: string;
  type: 'signal' | 'institution' | 'topic';
  count: number;
  researchers: TagResearcher[];
};

export const load: PageLoad = async ({ params, fetch }) => {
  const label = decodeURIComponent(params.label);
  const detail = await apiFetch<TagDetail>(
    `/tags/${encodeURIComponent(label)}`,
    fetch,
  );
  return {
    label,
    detail,
  };
};
