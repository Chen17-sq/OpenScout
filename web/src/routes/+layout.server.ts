import type { LayoutServerLoad } from './$types';
import type { Locale } from '$lib/translations';

const COOKIE_NAME = 'openscout_locale';

export const load: LayoutServerLoad = ({ cookies }) => {
  const v = cookies.get(COOKIE_NAME);
  const locale: Locale = v === 'en' ? 'en' : 'zh';
  return { locale };
};
