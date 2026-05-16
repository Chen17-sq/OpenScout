// Typed API client. Used by all SvelteKit load functions.

export const API_BASE = 'http://localhost:8000';

export type ResearcherSummary = {
  slug: string;
  name_en: string;
  name_zh: string | null;
  current_role: string | null;
  homepage_url: string | null;
  confidence_level: string;
};

export type PaperSummary = {
  arxiv_id: string | null;
  title: string;
  abstract: string | null;
  one_liner_zh: string | null;
  venue: string | null;
  pdf_url: string | null;
  published_at: string | null;
  n_authors: number;
  topics: string[];
};

export type StoryItem = {
  researcher: ResearcherSummary;
  paper: PaperSummary;
  reasoning: string | null;
};

export type BriefData = {
  brief_date: string;
  issue: number;
  kpi: {
    tracked: number;
    today_papers: number;
    today_emergences: number;
    soon_graduating: number;
    incoming_ap: number;
  };
  new_first_authors: StoryItem[];
  anchor_activity: StoryItem[];
  soon_graduating_picks: StoryItem[];
  incoming_ap_picks: StoryItem[];
  hot_papers: StoryItem[];
  sleeper_picks: StoryItem[];
};

// Investment Lens — top researchers under the user's three-pillar
// (breakthrough × commercial × buzz) framing. See work_scoring.py.
export type InvestmentPick = {
  slug: string;
  name_en: string;
  name_zh: string | null;
  country: string | null;
  current_role: string | null;
  score: number;
  top_paper: {
    arxiv_id: string | null;
    title: string;
    work_score: number;
    breakthrough: number;
    commercial: number;
    buzz: number;
    reasons: string[];
    position: number | null;
  } | null;
};

export type InvestmentPicks = {
  window_days: number;
  count: number;
  picks: InvestmentPick[];
};

export async function apiFetch<T = unknown>(
  path: string,
  fetchFn: typeof fetch = fetch,
): Promise<T | null> {
  try {
    const res = await fetchFn(`${API_BASE}${path}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function arxivUrl(id: string | null): string {
  return id ? `https://arxiv.org/abs/${id}` : '#';
}

export function blurb(text: string | null | undefined, max = 180): string {
  if (!text) return '';
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean.length <= max ? clean : clean.slice(0, max - 1).trimEnd() + '…';
}

export function roleLabel(role: string | null): string {
  if (!role) return '';
  const map: Record<string, string> = {
    phd: 'PhD',
    postdoc: 'Postdoc',
    incoming_ap: 'Incoming AP',
    ap: 'AP',
    associate: 'Associate',
    full: 'Full Prof',
    senior: 'Senior',
    industry: 'Industry',
  };
  return map[role] ?? role;
}
