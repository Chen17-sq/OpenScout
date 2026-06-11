// /notes is backed entirely by localStorage (private per-browser notes — see
// $lib/notes.ts), so there is nothing the server can render. Disable SSR to
// avoid hydration flashing an empty state; names are fetched client-side in
// +page.svelte, same idiom as /watchlist.
export const ssr = false;
