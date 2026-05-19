import Link from 'next/link';
import {
  ArrowLeft,
  Clock3,
  Database,
  Gauge,
  Layers3,
  MapPinned,
  MoonStar,
  Satellite,
} from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { Button } from '@/components/ui';

const DATASET_ICONS = {
  maps: MapPinned,
  timetable: Clock3,
  thailand: Database,
  delay: Gauge,
} as const;

const MAP_MODE_ICONS = {
  light: Layers3,
  dark: MoonStar,
  satellite: Satellite,
} as const;

export default async function OpenDataPage() {
  const t = await getTranslations();

  const datasetItems = [
    {
      key: 'maps',
      label: t('openDataPage.items.maps.label'),
      detail: t('openDataPage.items.maps.detail'),
      Icon: DATASET_ICONS.maps,
    },
    {
      key: 'timetable',
      label: t('openDataPage.items.timetable.label'),
      detail: t('openDataPage.items.timetable.detail'),
      Icon: DATASET_ICONS.timetable,
    },
    {
      key: 'thailand',
      label: t('openDataPage.items.thailand.label'),
      detail: t('openDataPage.items.thailand.detail'),
      Icon: DATASET_ICONS.thailand,
    },
    {
      key: 'delay',
      label: t('openDataPage.items.delay.label'),
      detail: t('openDataPage.items.delay.detail'),
      Icon: DATASET_ICONS.delay,
    },
  ];

  const mapModes = [
    {
      key: 'light',
      label: t('openDataPage.mapModes.light.label'),
      detail: t('openDataPage.mapModes.light.detail'),
      Icon: MAP_MODE_ICONS.light,
    },
    {
      key: 'dark',
      label: t('openDataPage.mapModes.dark.label'),
      detail: t('openDataPage.mapModes.dark.detail'),
      Icon: MAP_MODE_ICONS.dark,
    },
    {
      key: 'satellite',
      label: t('openDataPage.mapModes.satellite.label'),
      detail: t('openDataPage.mapModes.satellite.detail'),
      Icon: MAP_MODE_ICONS.satellite,
    },
  ];

  const notes = [
    t('openDataPage.notesList.refresh'),
    t('openDataPage.notesList.estimates'),
    t('openDataPage.notesList.coverage'),
    t('openDataPage.notesList.feedback'),
    t('openDataPage.notesList.official'),
  ];

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
                {t('openDataPage.back')}
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
          <p
            className="text-[11px] font-semibold tracking-[0.24em] uppercase"
            style={{ color: 'var(--panel-subtext)' }}
          >
            {t('openDataPage.eyebrow')}
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            {t('openDataPage.title')}
          </h1>
          <p
            className="mt-3 max-w-2xl text-sm leading-6"
            style={{ color: 'var(--panel-subtext)' }}
          >
            {t('openDataPage.description')}
          </p>
        </section>

        <section className="flex flex-col gap-3">
          <div className="px-1">
            <h2 className="text-sm font-semibold tracking-tight">
              {t('openDataPage.sections.datasets')}
            </h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {datasetItems.map(({ key, label, detail, Icon }) => (
              <article
                key={key}
                className="rounded-[24px] border px-4 py-4"
                style={{
                  background: 'var(--panel-bg-strong)',
                  borderColor: 'var(--panel-inner-ring)',
                  boxShadow: 'var(--panel-shadow)',
                }}
              >
                <div className="flex items-start gap-3">
                  <div
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl"
                    style={{
                      background: 'var(--panel-inner)',
                      color: 'var(--panel-text)',
                    }}
                  >
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold tracking-tight">
                      {label}
                    </h3>
                    <p
                      className="mt-2 text-sm leading-6"
                      style={{ color: 'var(--panel-subtext)' }}
                    >
                      {detail}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <div className="px-1">
            <h2 className="text-sm font-semibold tracking-tight">
              {t('openDataPage.sections.maps')}
            </h2>
          </div>
          <div className="grid gap-3">
            {mapModes.map(({ key, label, detail, Icon }) => (
              <article
                key={key}
                className="rounded-[24px] border px-4 py-4"
                style={{
                  background: 'var(--panel-bg-strong)',
                  borderColor: 'var(--panel-inner-ring)',
                  boxShadow: 'var(--panel-shadow)',
                }}
              >
                <div className="flex items-start gap-3">
                  <div
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl"
                    style={{
                      background: 'var(--panel-inner)',
                      color: 'var(--panel-text)',
                    }}
                  >
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold tracking-tight">
                      {label}
                    </h3>
                    <p
                      className="mt-2 text-sm leading-6"
                      style={{ color: 'var(--panel-subtext)' }}
                    >
                      {detail}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section
          className="rounded-[24px] border px-4 py-4"
          style={{
            background: 'var(--panel-bg-strong)',
            borderColor: 'var(--panel-inner-ring)',
            boxShadow: 'var(--panel-shadow)',
          }}
        >
          <h2 className="text-sm font-semibold tracking-tight">
            {t('openDataPage.sections.notes')}
          </h2>
          <ul className="mt-3 space-y-3">
            {notes.map((note) => (
              <li
                key={note}
                className="flex items-start gap-3 text-sm leading-6"
              >
                <span
                  className="mt-2 h-2 w-2 shrink-0 rounded-full"
                  style={{ background: 'var(--header-logo-bg)' }}
                />
                <span style={{ color: 'var(--panel-subtext)' }}>{note}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}
