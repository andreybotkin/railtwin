/**
 * Language switcher component.
 * Pattern inspired by trafimage-maps i18next language switching.
 */
'use client';

import { useTransition } from 'react';
import { useLocale } from 'next-intl';
import Cookies from 'js-cookie';
import { Button } from '@/components/ui';
import { cn } from '@/lib/utils';

const LOCALE_COOKIE = 'NEXT_LOCALE';

export default function LanguageSwitcher({ className }: { className?: string }) {
  const locale = useLocale();
  const [, startTransition] = useTransition();

  const toggleLocale = () => {
    const next = locale === 'en' ? 'th' : 'en';
    startTransition(() => {
      Cookies.set(LOCALE_COOKIE, next, { path: '/' });
      window.location.reload();
    });
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleLocale}
      title={locale === 'en' ? 'เปลี่ยนเป็นภาษาไทย' : 'Switch to English'}
      aria-label={locale === 'en' ? 'Switch to Thai' : 'Switch to English'}
      className={cn('rounded-2xl text-xs font-bold transition-colors', className)}
      style={{ color: 'var(--panel-subtext)' }}
    >
      {locale === 'en' ? 'TH' : 'EN'}
    </Button>
  );
}
