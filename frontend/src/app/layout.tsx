/**
 * Root layout for the application.
 */

import type { Metadata } from 'next';
import { Inter } from 'next/font/google';

import '@/styles/globals.css';
import Providers from './providers';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Thailand Railway Digital Twin',
  description:
    'Real-time visualization of Thailand railway network with train tracking',
  keywords: ['Thailand', 'Railway', 'Digital Twin', 'Train Tracking', 'SRT'],
  authors: [{ name: 'Thailand Railway Team' }],
  viewport: 'width=device-width, initial-scale=1',
  icons: {
    icon: '/favicon.ico',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
