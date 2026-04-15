/**
 * Station marker component for the map.
 */

'use client';

import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { CircleMarker, Popup } from 'react-leaflet';
import { Building2, CarFront, CreditCard, MapPin, UtensilsCrossed, Wifi } from 'lucide-react';

import type { Station } from '@/types';
import { Badge } from '@/components/ui';

interface StationMarkerProps {
  station: Station;
}

// Major stations that should be displayed larger
const MAJOR_STATIONS = ['BKK', 'BSG', 'CNX', 'HDY', 'UBN', 'NKI', 'PSL', 'NKR', 'SRT'];

export default function StationMarker({ station }: StationMarkerProps) {
  const isMajor = MAJOR_STATIONS.includes(station.code);

  // Convert [lon, lat] to [lat, lon] for Leaflet
  const position: [number, number] = [
    station.location.coordinates[1],
    station.location.coordinates[0],
  ];

  const radius = isMajor ? 8 : 5.5;

  return (
    <CircleMarker
      center={position}
      radius={radius}
      fillColor={isMajor ? '#0f172a' : '#f8fafc'}
      fillOpacity={0.96}
      color={isMajor ? '#f59e0b' : '#334155'}
      weight={isMajor ? 3 : 2}
      eventHandlers={{
        mouseover: (event) => event.target.openPopup(),
      }}
    >
      <Popup>
        <div className="min-w-[220px] space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold tracking-tight">{station.name}</h3>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                <MapPin className="h-4 w-4" />
                <span>{station.code}</span>
              </div>
            </div>
            {station.name_th && (
              <Badge variant="outline" className="border-zinc-300 text-zinc-700">
                {station.name_th}
              </Badge>
            )}
          </div>

          <div className="rounded-2xl bg-zinc-50 p-3 text-sm">
            <div className="flex items-center gap-2 text-zinc-500">
              <Building2 className="h-4 w-4" />
              <span>{[station.city, station.province].filter(Boolean).join(', ') || 'Station in network'}</span>
            </div>
          </div>

          {station.facilities && (
            <div className="flex flex-wrap gap-2 pt-1">
              {station.facilities.parking && (
                <FacilityChip icon={<CarFront className="h-3.5 w-3.5" />} label="Parking" />
              )}
              {station.facilities.wifi && (
                <FacilityChip icon={<Wifi className="h-3.5 w-3.5" />} label="Wi-Fi" />
              )}
              {station.facilities.restaurant && (
                <FacilityChip icon={<UtensilsCrossed className="h-3.5 w-3.5" />} label="Food" />
              )}
              {station.facilities.atm && (
                <FacilityChip icon={<CreditCard className="h-3.5 w-3.5" />} label="ATM" />
              )}
            </div>
          )}

          {isMajor && (
            <Badge variant="secondary" className="rounded-full">
              Major interchange
            </Badge>
          )}
        </div>
      </Popup>
    </CircleMarker>
  );
}

function FacilityChip({
  icon,
  label,
}: {
  icon: ReactNode;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-xs text-zinc-700">
      {icon}
      {label}
    </span>
  );
}
