/**
 * Root layout for the application.
 */

import type { Metadata, Viewport } from 'next';
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';

import '@/styles/globals.css';
import Providers from './providers';

export const metadata: Metadata = {
  title: 'Thailand Railway Digital Twin',
  description:
    'Real-time visualization of Thailand railway network with train tracking',
  keywords: ['Thailand', 'Railway', 'Digital Twin', 'Train Tracking', 'SRT'],
  authors: [{ name: 'Thailand Railway Team' }],
  icons: {
    icon: '/favicon.ico',
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

  return (
    <html lang={locale} suppressHydrationWarning>
      <body>
        <NextIntlClientProvider messages={messages}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
