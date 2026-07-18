import type { Metadata } from 'next';

export const SITE_URL = 'https://rthfi.com';
export const SITE_NAME = 'Thailand Railway Digital Twin';

export const primaryKeywords = [
  'Thailand train tracker',
  'Thailand railway map',
  'Thailand train map',
  'SRT train timetable',
  'Thailand train schedule',
  'State Railway of Thailand map',
  'live train map Thailand',
  'ติดตามรถไฟไทย',
  'ตารางรถไฟ',
  'แผนที่รถไฟไทย',
];

export const defaultDescription =
  'Explore an interactive Thailand railway map with simulated train positions, SRT timetable data, routes, stations, journey progress and delay estimates.';

export function pageMetadata({
  title,
  description,
  path,
  keywords = [],
}: {
  title: string;
  description: string;
  path: string;
  keywords?: string[];
}): Metadata {
  const canonical = path === '/' ? SITE_URL : `${SITE_URL}${path}`;

  return {
    title,
    description,
    keywords: [...primaryKeywords, ...keywords],
    alternates: { canonical },
    openGraph: {
      type: 'website',
      url: canonical,
      siteName: SITE_NAME,
      title,
      description,
      locale: 'en_US',
      alternateLocale: ['th_TH'],
      images: [
        {
          url: '/opengraph-image',
          width: 1200,
          height: 630,
          alt: 'Interactive map of Thailand railway routes and trains',
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: ['/opengraph-image'],
    },
  };
}
