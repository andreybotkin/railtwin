/**
 * Train list panel component.
 */

'use client';

import { useState, useMemo } from 'react';
import { Train as TrainIcon, Search, Circle, Clock } from 'lucide-react';

import { useTrainPositions, useInitialPositions, useTrains } from '@/lib/hooks';
import { formatSpeed, formatDelay, getTrainTypeName, cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, Input, Badge } from '@/components/ui';
import type { TrainPositionUpdate } from '@/types';

interface TrainInfoPanelProps {
  onTrainSelect?: (trainId: number) => void;
  selectedTrainId?: number | null;
}

export default function TrainInfoPanel({
  onTrainSelect,
  selectedTrainId,
}: TrainInfoPanelProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const { positions: wsPositions, isConnected } = useTrainPositions();
  const { data: apiPositions } = useInitialPositions();
  const { data: trainsData } = useTrains();

  const positions = useMemo(() => {
    if (isConnected && wsPositions.length > 0) {
      return wsPositions;
    }
    return apiPositions || [];
  }, [isConnected, wsPositions, apiPositions]);

  const filteredPositions = useMemo(() => {
    if (!searchQuery) return positions;
    const query = searchQuery.toLowerCase();
    return positions.filter(
      (p) =>
        p.train_number.toLowerCase().includes(query) ||
        p.next_station?.toLowerCase().includes(query)
    );
  }, [positions, searchQuery]);

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <TrainIcon className="h-5 w-5" />
            Active Trains
          </CardTitle>
          <Badge variant={isConnected ? 'success' : 'secondary'}>
            <Circle
              className={cn(
                'h-2 w-2 mr-1',
                isConnected ? 'fill-current' : 'fill-none'
              )}
            />
            {isConnected ? 'Live' : 'Polling'}
          </Badge>
        </div>
        <div className="relative mt-2">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search trains..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-auto p-0">
        <div className="space-y-1 p-3">
          {filteredPositions.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No active trains found
            </div>
          ) : (
            filteredPositions.map((position) => (
              <TrainListItem
                key={position.train_id}
                position={position}
                isSelected={selectedTrainId === position.train_id}
                onClick={() => onTrainSelect?.(position.train_id)}
              />
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}

interface TrainListItemProps {
  position: TrainPositionUpdate;
  isSelected: boolean;
  onClick: () => void;
}

function TrainListItem({ position, isSelected, onClick }: TrainListItemProps) {
  const statusColor =
    position.status === 'moving'
      ? 'bg-green-500'
      : position.status === 'delayed'
      ? 'bg-red-500'
      : position.status === 'at_station'
      ? 'bg-blue-500'
      : 'bg-gray-500';

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left p-3 rounded-lg transition-colors',
        'hover:bg-accent',
        isSelected && 'bg-accent ring-2 ring-primary'
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className={cn('h-3 w-3 rounded-full', statusColor)} />
          <span className="font-semibold">Train {position.train_number}</span>
        </div>
        <Badge variant="outline" className="text-xs">
          {getTrainTypeName(position.train_type)}
        </Badge>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-muted-foreground">
        <div className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatSpeed(position.speed)}
        </div>
        <div
          className={cn(
            'text-right',
            position.delay_minutes > 0 ? 'text-red-500' : 'text-green-600'
          )}
        >
          {formatDelay(position.delay_minutes)}
        </div>
      </div>

      {position.next_station && (
        <div className="mt-1 text-sm truncate">
          <span className="text-muted-foreground">Next: </span>
          <span className="font-medium">{position.next_station}</span>
        </div>
      )}
    </button>
  );
}
