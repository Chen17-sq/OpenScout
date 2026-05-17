import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

export type TagOverviewSignal = { label: string; label_zh?: string | null; count: number };
export type TagOverviewInstitution = { label: string; country?: string | null; count: number };
export type TagOverviewTopic = {
  label: string;
  count: number;
  level?: number | null;
};

export type TagOverview = {
  signal: TagOverviewSignal[];
  institution: TagOverviewInstitution[];
  topic: TagOverviewTopic[];
};

export const load: PageLoad = async ({ fetch }) => {
  const overview = await apiFetch<TagOverview>('/tags', fetch);
  return {
    overview: overview ?? { signal: [], institution: [], topic: [] },
  };
};
