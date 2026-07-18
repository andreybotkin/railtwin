import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, ShieldCheck } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { Button } from '@/components/ui';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  robots: { index: false, follow: true },
};

const PRIVACY_SECTION_KEYS = [
  'overview',
  'informationProcessed',
  'howWeUseInformation',
  'cookiesAndAnalytics',
  'sharingAndRetention',
  'yourChoices',
  'policyUpdates',
] as const;

export default async function PrivacyPolicyPage() {
  const t = await getTranslations();
  const privacySections = PRIVACY_SECTION_KEYS.map((key) => ({
    key,
    title: t(`privacyPolicyPage.sections.${key}.title`),
    body: t(`privacyPolicyPage.sections.${key}.body`),
  }));

  return (
    <main
      className="min-h-dvh"
      style={{ background: 'var(--page-bg)', color: 'var(--panel-text)' }}
    >
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-4 pb-8 sm:px-6 sm:py-6">
        <div className="sticky top-0 z-20 -mx-1 px-1 pt-1 pb-2">
          <div
            className="rounded-3xl border p-2 backdrop-blur-xl"
            style={{
              background: 'var(--panel-bg)',
              borderColor: 'var(--panel-border)',
              boxShadow: 'var(--panel-shadow)',
            }}
          >
            <Button
              asChild
              variant="ghost"
              className="h-12 w-full justify-start rounded-2xl px-4 text-sm"
              style={{ color: 'var(--panel-text)' }}
            >
              <Link href="/">
                <ArrowLeft className="mr-2 h-4 w-4" />
                {t('legal.backToMap')}
              </Link>
            </Button>
          </div>
        </div>

        <section
          className="rounded-[28px] border px-4 py-5 sm:px-6"
          style={{
            background: 'var(--panel-bg)',
            borderColor: 'var(--panel-border)',
            boxShadow: 'var(--panel-shadow)',
          }}
        >
          <div className="flex items-start gap-3">
            <div
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl"
              style={{
                background: 'var(--panel-inner)',
                color: 'var(--panel-text)',
              }}
            >
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <p
                className="text-[11px] font-semibold tracking-[0.24em] uppercase"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {t('legal.eyebrow')}
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                {t('privacyPolicyPage.title')}
              </h1>
              <p
                className="mt-3 text-sm leading-6"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {t('legal.lastUpdated')}. {t('privacyPolicyPage.description')}
              </p>
            </div>
          </div>
        </section>

        <section className="flex flex-col gap-3">
          {privacySections.map((section) => (
            <article
              key={section.key}
              className="rounded-[24px] border px-4 py-4"
              style={{
                background: 'var(--panel-bg-strong)',
                borderColor: 'var(--panel-inner-ring)',
                boxShadow: 'var(--panel-shadow)',
              }}
            >
              <h2 className="text-sm font-semibold tracking-tight">
                {section.title}
              </h2>
              <p
                className="mt-2 text-sm leading-6"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {section.body}
              </p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
