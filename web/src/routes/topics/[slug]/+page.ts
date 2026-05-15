import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';

type TopicDetail = {
  slug: string;
  name: string;
  name_zh: string | null;
  description: string | null;
  recent_papers: Array<{
    arxiv_id: string | null;
    title: string;
    abstract: string | null;
    published_at: string | null;
    first_seen_at: string | null;
  }>;
  top_first_authors: Array<{
    slug: string;
    name_en: string;
    name_zh: string | null;
    current_role: string | null;
    confidence_level: string;
    n_papers: number;
  }>;
  trend_7d: Array<{ date: string; n: number }>;
};

export const load: PageLoad = async ({ params, fetch }) => {
  const topic = await apiFetch<TopicDetail>(`/topics/${params.slug}`, fetch);
  if (!topic) throw error(404, `topic ${params.slug} not found`);
  return { topic };
};
