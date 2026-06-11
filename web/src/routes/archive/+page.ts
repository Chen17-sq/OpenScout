import { redirect } from '@sveltejs/kit';

// /archive is a legacy alias — the nav links to /editions, but external links
// and muscle memory still hit /archive. Permanent redirect, no page body.
export const load = () => {
  throw redirect(301, '/editions');
};
