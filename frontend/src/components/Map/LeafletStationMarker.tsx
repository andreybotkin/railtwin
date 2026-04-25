'use client';

/**
 * Leaflet station marker — white circle with black border.
 *
 * - No hover popup (removed per design spec).
 * - Click → selectStation(station.id) to open the StationInfoSheet panel.
 */

import { useMemo } from 'react';
import { CircleMarker, Tooltip } from 'react-leaflet';
import { useLocale } from 'next-intl';

import type { Station } from '@/types';
import { useRailwayStore } from '@/lib/stores/railway-store';

interface LeafletStationMarkerProps {
  station: Station;
}

// Well-known major interchange stations
const MAJOR_STATIONS = ['BKK', 'BSG', 'CNX', 'HDY', 'UBN', 'NKI', 'PSL', 'NKR', 'SRT'];

export default function LeafletStationMarker({ station }: LeafletStationMarkerProps) {
  const selectStation = useRailwayStore((s) => s.selectStation);
  const selectedStationId = useRailwayStore((s) => s.selectedStationId);
  const isMajor = MAJOR_STATIONS.includes(station.code);
  const locale = useLocale();

  const isSelected = station.id === selectedStationId;

  // GeoJSON [lon, lat] → Leaflet [lat, lon]
  const position = useMemo<[number, number]>(
    () => [station.location.coordinates[1], station.location.coordinates[0]],
    [station.location.coordinates],
  );

  const radius = isMajor ? 8 : 5.5;
  const strokeWeight = isMajor ? 2.5 : 1.8;

  const displayName = locale === 'th' && station.name_th ? station.name_th : station.name;

  return (
    <CircleMarker
      center={position}
      radius={radius}
      fillColor="#ffffff"
      fillOpacity={1}
      color="#1a1a1a"
      weight={strokeWeight}
      eventHandlers={{
        click: () => selectStation(station.id),
      }}
    >
      {isSelected && (
        <Tooltip
          permanent
          direction="top"
          offset={[0, -(radius + 4)]}
          className="station-name-badge"
        >
          {displayName}
        </Tooltip>
      )}
    </CircleMarker>
  );
}

