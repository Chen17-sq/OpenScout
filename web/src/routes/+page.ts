import type { PageLoad } from './$types';
import { apiFetch, type BriefData, type InvestmentPicks } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
  const [brief, investment] = await Promise.all([
    apiFetch<BriefData>('/briefs/today', fetch),
    apiFetch<InvestmentPicks>('/investment/picks?limit=8&window_days=30', fetch),
  ]);
  return { brief, investment };
};
