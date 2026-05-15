import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { apiFetch, type BriefData } from '$lib/api';

export const load: PageLoad = async ({ params, fetch }) => {
  const brief = await apiFetch<BriefData>(
    `/briefs/by-date/${params.date}/structured`,
    fetch,
  );
  if (!brief) throw error(404, `no brief for ${params.date}`);
  return { brief };
};
