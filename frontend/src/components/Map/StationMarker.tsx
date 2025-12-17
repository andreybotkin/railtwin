/**
 * Station marker component for the map.
 */

'use client';

import { useMemo } from 'react';
import { CircleMarker, Popup } from 'react-leaflet';

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

  return (
    <CircleMarker
      center={position}
      radius={isMajor ? 8 : 5}
      fillColor={isMajor ? '#1E88E5' : '#666666'}
      fillOpacity={0.9}
      color="#ffffff"
      weight={isMajor ? 3 : 2}
    >
      <Popup>
        <div className="min-w-[180px] space-y-2">
          <div>
            <h3 className="text-lg font-bold">{station.name}</h3>
            {station.name_th && (
              <p className="text-sm text-muted-foreground">{station.name_th}</p>
            )}
          </div>

          <div className="text-sm">
            <Badge variant="outline" className="mr-1">
              {station.code}
            </Badge>
            {isMajor && (
              <Badge variant="secondary">Major Station</Badge>
            )}
          </div>

          {(station.city || station.province) && (
            <p className="text-sm text-muted-foreground">
              {[station.city, station.province].filter(Boolean).join(', ')}
            </p>
          )}

          {station.facilities && (
            <div className="flex flex-wrap gap-1 pt-1 border-t">
              {station.facilities.parking && (
                <Badge variant="outline" className="text-xs">🅿️ Parking</Badge>
              )}
              {station.facilities.wifi && (
                <Badge variant="outline" className="text-xs">📶 WiFi</Badge>
              )}
              {station.facilities.restaurant && (
                <Badge variant="outline" className="text-xs">🍴 Food</Badge>
              )}
              {station.facilities.atm && (
                <Badge variant="outline" className="text-xs">💳 ATM</Badge>
              )}
            </div>
          )}
        </div>
      </Popup>
    </CircleMarker>
  );
}
