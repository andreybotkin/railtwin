import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Thailand Railway Digital Twin',
    short_name: 'RailTwin',
    description:
      'Interactive Thailand railway map with simulated train tracking, routes, stations and timetable data.',
    start_url: '/',
    display: 'standalone',
    background_color: '#09090b',
    theme_color: '#18181b',
    lang: 'en',
    categories: ['travel', 'navigation', 'maps'],
    icons: [
      {
        src: '/icon.svg',
        sizes: 'any',
        type: 'image/svg+xml',
        purpose: 'any',
      },
    ],
  };
}
