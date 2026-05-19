/**
 * Schedule panel component.
 */

'use client';

import { useState, useMemo } from 'react';
import { Calendar, MapPin } from 'lucide-react';

import { useRoutes, useStations } from '@/lib/hooks';
import { getRouteTypeName, cn } from '@/lib/utils';

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Badge,
} from '@/components/ui';
import type { Route, Station } from '@/types';

interface SchedulePanelProps {
  className?: string;
}

export default function SchedulePanel({ className }: SchedulePanelProps) {
  const [activeTab, setActiveTab] = useState('routes');
  const { data: routesData, isLoading: routesLoading } = useRoutes();
  const { data: stationsData, isLoading: stationsLoading } = useStations();

  const routes = routesData?.items || [];
  const stations = stationsData?.items || [];

  return (
    <Card
      className={cn(
        'flex h-full flex-col rounded-none border-0 bg-transparent shadow-none',
        className
      )}
    >
      <CardHeader className="border-b border-zinc-200/80 pt-4 pb-3">
        <CardTitle className="flex items-center gap-2 text-lg text-zinc-950">
          <Calendar className="h-5 w-5" />
          Information
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden p-0">
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex h-full flex-col"
        >
          <TabsList className="mx-3 mt-3 grid w-auto grid-cols-2 rounded-2xl bg-zinc-100">
            <TabsTrigger value="routes">Routes</TabsTrigger>
            <TabsTrigger value="stations">Stations</TabsTrigger>
          </TabsList>

          <TabsContent
            value="routes"
            className="m-0 flex-1 overflow-auto p-3 pt-0"
          >
            {routesLoading ? (
              <div className="text-muted-foreground py-8 text-center">
                Loading routes...
              </div>
            ) : (
              <RouteList routes={routes} />
            )}
          </TabsContent>

          <TabsContent
            value="stations"
            className="m-0 flex-1 overflow-auto p-3 pt-0"
          >
            {stationsLoading ? (
              <div className="text-muted-foreground py-8 text-center">
                Loading stations...
              </div>
            ) : (
              <StationList stations={stations} />
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

interface RouteListProps {
  routes: Route[];
}

function RouteList({ routes }: RouteListProps) {
  if (routes.length === 0) {
    return (
      <div className="text-muted-foreground py-8 text-center">
        No routes available
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2">
      {routes.map((route) => (
        <div
          key={route.id}
          className="bg-card hover:bg-accent rounded-lg border p-3 transition-colors"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <div
                className="h-4 w-4 flex-shrink-0 rounded-full"
                style={{ backgroundColor: route.color || '#666' }}
              />
              <div>
                <h4 className="font-semibold">{route.name}</h4>
                {route.name_th && (
                  <p className="text-muted-foreground text-sm">
                    {route.name_th}
                  </p>
                )}
              </div>
            </div>
            <Badge variant="outline">
              {getRouteTypeName(route.route_type)}
            </Badge>
          </div>

          <div className="text-muted-foreground mt-2 flex items-center gap-4 text-sm">
            <span>{route.distance_km} km</span>
            <span>{route.stations?.length || 0} stations</span>
          </div>

          {route.stations && route.stations.length > 0 && (
            <div className="mt-2 text-sm">
              <span className="text-muted-foreground">Route: </span>
              <span>
                {route.stations[0].name} →{' '}
                {route.stations[route.stations.length - 1].name}
              </span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

interface StationListProps {
  stations: Station[];
}

function StationList({ stations }: StationListProps) {
  const [filter, setFilter] = useState('');

  const filteredStations = useMemo(() => {
    if (!filter) return stations;
    const query = filter.toLowerCase();
    return stations.filter(
      (s) =>
        s.name.toLowerCase().includes(query) ||
        s.code.toLowerCase().includes(query) ||
        s.city?.toLowerCase().includes(query)
    );
  }, [stations, filter]);

  if (stations.length === 0) {
    return (
      <div className="text-muted-foreground py-8 text-center">
        No stations available
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2">
      <input
        type="text"
        placeholder="Search stations..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="bg-background w-full rounded-md border px-3 py-2 text-sm"
      />

      <div className="max-h-[400px] space-y-1 overflow-auto">
        {filteredStations.map((station) => (
          <div
            key={station.id}
            className="hover:bg-accent flex items-center gap-2 rounded-lg p-2 transition-colors"
          >
            <MapPin className="text-muted-foreground h-4 w-4 flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-medium">{station.name}</span>
                <Badge variant="outline" className="flex-shrink-0 text-xs">
                  {station.code}
                </Badge>
              </div>
              {station.province && (
                <p className="text-muted-foreground truncate text-xs">
                  {station.province}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
