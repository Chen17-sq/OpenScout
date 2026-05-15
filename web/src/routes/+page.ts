import type { PageLoad } from './$types';

const API_BASE = 'http://localhost:8000';

export const load: PageLoad = async ({ fetch }) => {
  try {
    const res = await fetch(`${API_BASE}/briefs/latest`);
    if (!res.ok) {
      return { brief: null, error: `Backend returned ${res.status}` };
    }
    const brief = await res.json();
    return { brief, error: null };
  } catch (err) {
    return {
      brief: null,
      error: `Backend not reachable at ${API_BASE} — start it with: make api`,
    };
  }
};
