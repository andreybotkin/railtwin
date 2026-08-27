const CARTO_API_KEY = process.env.NEXT_PUBLIC_CARTO_API_KEY || '';

/**
 * CARTO basemap requests are made directly by the browser, so the API key is
 * embedded in the frontend bundle at build time.
 */
export function cartoTileUrl(path: string): string {
  const baseUrl = `https://{s}.basemaps.cartocdn.com/${path}`;

  if (!CARTO_API_KEY) return baseUrl;

  return `${baseUrl}?key=${encodeURIComponent(CARTO_API_KEY)}`;
}

/** MapLibre does not expand Leaflet's {s} subdomain placeholder. */
export function cartoTileUrls(path: string): string[] {
  return ['a', 'b', 'c', 'd'].map((subdomain) =>
    cartoTileUrl(path).replace('{s}', subdomain)
  );
}
