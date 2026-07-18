/**
 * Root layout for the application.
 */

import type { Metadata, Viewport } from 'next';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';

import '@/styles/globals.css';
import {
  defaultDescription,
  pageMetadata,
  SITE_NAME,
  SITE_URL,
} from '@/lib/seo';
import Providers from './providers';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  ...pageMetadata({
    title: 'Thailand Train Tracker & Railway Map | RailTwin',
    description: defaultDescription,
    path: '/',
  }),
  title: {
    default: 'Thailand Train Tracker & Railway Map | RailTwin',
    template: '%s | RailTwin',
  },
  applicationName: SITE_NAME,
  authors: [
    {
      name: 'RailTwin contributors',
      url: 'https://github.com/andreybotkin/railtwin',
    },
  ],
  creator: 'RailTwin contributors',
  publisher: 'RailTwin',
  category: 'travel',
  referrer: 'origin-when-cross-origin',
  formatDetection: { telephone: false, address: false, email: false },
  manifest: '/manifest.webmanifest',
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-image-preview': 'large',
      'max-snippet': -1,
      'max-video-preview': -1,
    },
  },
  verification: {
    google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION,
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();
  const structuredData = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': `${SITE_URL}/#website`,
        url: SITE_URL,
        name: SITE_NAME,
        description: defaultDescription,
        inLanguage: ['en', 'th'],
      },
      {
        '@type': 'WebApplication',
        '@id': `${SITE_URL}/#application`,
        name: SITE_NAME,
        url: SITE_URL,
        description: defaultDescription,
        applicationCategory: 'TravelApplication',
        operatingSystem: 'Any',
        browserRequirements: 'Requires JavaScript and a modern web browser',
        isAccessibleForFree: true,
        areaServed: { '@type': 'Country', name: 'Thailand' },
        inLanguage: ['en', 'th'],
        offers: { '@type': 'Offer', price: 0, priceCurrency: 'THB' },
      },
    ],
  };

  return (
    <html lang={locale} suppressHydrationWarning>
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(structuredData).replace(/</g, '\\u003c'),
          }}
        />
        <NextIntlClientProvider messages={messages}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
