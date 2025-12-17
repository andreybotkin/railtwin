/**
 * Train marker component for the map.
 */

'use client';

import { useMemo } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { Train } from 'lucide-react';
import { renderToStaticMarkup } from 'react-dom/server';

import type { TrainPositionUpdate } from '@/types';
import {
  getRouteColor,
  formatSpeed,
  formatDelay,
  getTrainTypeName,
  getStatusColor,
} from '@/lib/utils';
import { Badge } from '@/components/ui';

interface TrainMarkerProps {
  position: TrainPositionUpdate;
}

export default function TrainMarker({ position }: TrainMarkerProps) {
  // Create custom icon for train marker
  const icon = useMemo(() => {
    const color = position.train_type === 'special_express' 
      ? '#E53935' 
      : position.train_type === 'rapid'
      ? '#1E88E5'
      : '#43A047';

    const iconHtml = `
      <div class="train-icon ${position.status === 'moving' ? 'moving' : ''}" 
           style="background-color: ${color}; transform: rotate(${position.heading || 0}deg)">
        🚂
      </div>
    `;

    return L.divIcon({
      html: iconHtml,
      className: 'train-marker',
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -14],
    });
  }, [position.train_type, position.status, position.heading]);

  // Convert [lon, lat] to [lat, lon] for Leaflet
  const markerPosition: [number, number] = [
    position.location.coordinates[1],
    position.location.coordinates[0],
  ];

  const statusBadgeVariant = 
    position.status === 'moving' ? 'success' :
    position.status === 'delayed' ? 'destructive' :
    position.status === 'at_station' ? 'info' : 'secondary';

  return (
    <Marker position={markerPosition} icon={icon}>
      <Popup>
        <div className="min-w-[200px] space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold">Train {position.train_number}</h3>
            <Badge variant={statusBadgeVariant} className="capitalize">
              {position.status.replace('_', ' ')}
            </Badge>
          </div>
          
          <div className="text-sm space-y-1">
            <p className="text-muted-foreground">
              {getTrainTypeName(position.train_type)}
            </p>
            
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-muted-foreground">Speed:</span>
                <span className="ml-1 font-medium">{formatSpeed(position.speed)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Delay:</span>
                <span className={`ml-1 font-medium ${position.delay_minutes > 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {formatDelay(position.delay_minutes)}
                </span>
              </div>
            </div>

            {position.next_station && (
              <div className="pt-2 border-t">
                <span className="text-muted-foreground">Next station:</span>
                <p className="font-medium">{position.next_station}</p>
              </div>
            )}

            {position.progress !== undefined && (
              <div className="pt-1">
                <div className="flex justify-between text-xs">
                  <span>Journey progress</span>
                  <span>{position.progress}%</span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden mt-1">
                  <div 
                    className="h-full bg-primary transition-all"
                    style={{ width: `${position.progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </Popup>
    </Marker>
  );
}
