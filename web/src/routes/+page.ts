import type { PageLoad } from './$types';
import { apiFetch, type BriefData } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const brief = await apiFetch<BriefData>('/briefs/today', fetch);
  return { brief };
};
