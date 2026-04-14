https://www.thaitrainguide.com/tracking/

Here are some sample links from the train tracking website:

[1] Special Express No.9 to Chiang Mai: https://ttsview.railway.co.th/searchresult_2023.php?trainno=9&lang=eng

In the above link, just change the train number 9 to any train that you want to track.

[2] Timetable for Special Express No.9: https://ttsview.railway.co.th/TimeTable-for-TTS.php?TrainNo=9

This is the timetable for No.9 train. Just change to a different number to see your own train. Unfortunately it is only in Thai.

[3] Live tracking for train No.9 on 23rd April 2024: https://ttsview.railway.co.th/searchresult_2023.php?trainno=9&date=23-04-2024&lang=eng

I find this link useful as it gives you an idea if the train has a history of arriving on time. In the link, just change the train number and the date you want to check.


I'll provide a thorough exploration of the frontend codebase with actual implementation details.

## **Frontend Codebase Structure & Architecture**

### **Directory Overview**

```
src/
├── app/
│   ├── layout.tsx          (Root layout with providers)
│   ├── page.tsx            (Homepage)
│   └── providers.tsx       (QueryClient setup)
├── components/
│   ├── LanguageSwitcher.tsx
│   ├── Map/               (Core map components)
│   │   ├── MapContainer.tsx      (Dynamic wrapper, SSR-safe)
│   │   ├── MapContent.tsx        (Main map implementation)
│   │   ├── CanvasTrainLayer.tsx  (Canvas-rendered trains 1000+)
│   │   ├── TrainMarker.tsx       (Rich DOM marker, selected train)
│   │   ├── StationMarker.tsx     
│   │   ├── LayerTree.tsx         (Topic/layer tree UI)
│   │   ├── RailwayMapElement.tsx (Web Component wrapper)
│   │   └── index.ts
│   ├── Schedule/
│   ├── TrainInfo/
│   └── ui/                (shadcn components)
├── lib/
│   ├── api/
│   │   └── client.ts      (Axios API client for stations/routes/trains/schedules)
│   ├── hooks/
│   │   └── index.ts       (useTrainPositions, useRoutes, useStations, etc.)
│   ├── stores/
│   │   └── map-topic-store.ts  (Zustand: topics, layers, zoom, generalization)
│   ├── utils/
│   │   └── index.ts       (formatSpeed, getDelayColor, cn, etc.)
│   ├── websocket.ts       (TrainWebSocketClient singleton)
│   └── map-topics.ts      (Topic definitions, zoom generalization rules)
├── types/
│   ├── index.ts           (TrainPositionUpdate, types, WebSocketMessage)
│   ├── map-topics.ts      (MapLayer, MapTopic, ZoomGeneralization)
│   └── leaflet-extensions.d.ts
└── i18n.ts
```

---

## **1. Train Marker Animation Implementation**

### **TrainMarker.tsx** — Rich DOM Component (Selected Train)
[TrainMarker.tsx](frontend/src/components/Map/TrainMarker.tsx#L1-L150)

**Key animation approach:**
```typescript
// Animation duration matches WebSocket update interval (2s)
const ANIM_DURATION_MS = 1900;

// Smooth interpolation via requestAnimationFrame
useEffect(() => {
  const targetLat = position.location.coordinates[1];
  const targetLon = position.location.coordinates[0];
  const [startLat, startLon] = displayPosRef.current;
  const startTime = performance.now();

  function step(now: number) {
    const t = Math.min((now - startTime) / ANIM_DURATION_MS, 1);
    const lat = startLat + (targetLat - startLat) * t;
    const lon = startLon + (targetLon - startLon) * t;
    displayPosRef.current = [lat, lon];
    markerRef.current?.setLatLng([lat, lon]);
    if (t < 1) {
      animRef.current = requestAnimationFrame(step);
    }
  }

  animRef.current = requestAnimationFrame(step);
  return () => cancelAnimationFrame(animRef.current);
}, [position.location.coordinates[0], position.location.coordinates[1]]);
```

**Delay color coding** (geops mobility-toolbox-js pattern):
```typescript
function getDelayColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return '#43A047';   // green
  if (delayMinutes <= 5) return '#FDD835';   // yellow
  if (delayMinutes <= 15) return '#FB8C00';  // orange
  return '#E53935';                          // red
}

const delayBadge = position.delay_minutes > 0
  ? `<span style="...background:${delayColor};...">+${position.delay_minutes}</span>`
  : '';
```

---

### **CanvasTrainLayer.tsx** — Performance-Optimized Canvas Layer

[CanvasTrainLayer.tsx](frontend/src/components/Map/CanvasTrainLayer.tsx#L1-L250)

**Pattern from geops mobility-toolbox-js RealtimeEngine:**
```typescript
// Animation state tracking for each train
interface TrainAnimState {
  marker: L.CircleMarker;
  prevLat: number;
  prevLon: number;
  targetLat: number;
  targetLon: number;
  startTime: number;
}

// requestAnimationFrame loop for 1000+ trains
useEffect(() => {
  const states = animStates.current;

  function animate() {
    const now = performance.now();
    states.forEach((state) => {
      const t = Math.min((now - state.startTime) / ANIM_DURATION, 1);
      if (t < 1) {
        const lat = state.prevLat + (state.targetLat - state.prevLat) * t;
        const lon = state.prevLon + (state.targetLon - state.prevLon) * t;
        state.marker.setLatLng([lat, lon]);
      }
    });
    rafId.current = requestAnimationFrame(animate);
  }

  rafId.current = requestAnimationFrame(animate);
  return () => cancelAnimationFrame(rafId.current);
}, []);

// Uses L.Canvas renderer for lightweight rendering
const canvasRenderer = L.canvas({ padding: 0.5 });
const marker = L.circleMarker([lat, lon], {
  renderer: canvasRenderer,
  radius: 5,
  fillColor: getDelayColor(pos.delay_minutes),
  color: TYPE_COLORS[pos.train_type],
  weight: 2,
  interactive: true,
});
```

---

## **2. WebSocket Client Implementation**

### **websocket.ts** — Full WebSocket Client
[websocket.ts](frontend/src/lib/websocket.ts#L1-L300)

**Core connection with reconnect & heartbeat:**
```typescript
export class TrainWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private currentBBox: string | null = null;

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.shouldReconnect = true;
    this.ws = new WebSocket(`${WS_BASE_URL}/ws/trains`);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      this.setupVisibilityHandler();
      // Re-send BBOX on reconnect
      if (this.currentBBox) {
        this.sendBBox(this.currentBBox);
      }
    };

    this.ws.onmessage = (event) => {
      const message: WebSocketMessage = JSON.parse(event.data);
      if (message.type === 'positions' && Array.isArray(message.data)) {
        this.onMessageHandlers.forEach((handler) => {
          handler(message.data as TrainPositionUpdate[]);
        });
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.onErrorHandlers.forEach((handler) => handler(error));
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.stopHeartbeat();
      if (this.shouldReconnect) {
        this.attemptReconnect();
      }
    };
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnection attempts reached');
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    setTimeout(() => this.connect(), delay);
  }
}
```

**Heartbeat with Visibility API** (geops pattern):
```typescript
private startHeartbeat(): void {
  this.heartbeatInterval = setInterval(() => {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping');
    }
  }, HEARTBEAT_INTERVAL_MS); // 10s
}

private setupVisibilityHandler(): void {
  this.visibilityHandler = () => {
    if (document.hidden) {
      // Tab hidden — pause heartbeat to save resources
      this.stopHeartbeat();
    } else {
      // Tab visible — restart heartbeat and reconnect if needed
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.startHeartbeat();
        if (this.currentBBox) {
          this.sendBBox(this.currentBBox);
        }
      } else if (this.shouldReconnect) {
        this.reconnectAttempts = 0;
        this.connect();
      }
    }
  };

  document.addEventListener('visibilitychange', this.visibilityHandler);
}
```

**BBOX Server-Side Filtering** (mobility-toolbox-js pattern):
```typescript
sendBBox(bbox: string): void {
  this.currentBBox = bbox;
  if (this.ws?.readyState === WebSocket.OPEN) {
    this.ws.send(`BBOX ${bbox}`);
  }
}
```

---

## **3. Map Component Structure**

### **MapContainer.tsx** — SSR-Safe Entry Point
[MapContainer.tsx](frontend/src/components/Map/MapContainer.tsx#L1-L50)

```typescript
// Dynamic import to avoid SSR issues with Leaflet
const MapContent = dynamic(() => import('./MapContent'), {
  ssr: false,
  loading: () => <Loader2 className="h-8 w-8 animate-spin" />,
});
```

### **MapContent.tsx** — Main Implementation
[MapContent.tsx](frontend/src/components/Map/MapContent.tsx#L1-L400)

**Core map breakdown:**
```typescript
export default function MapContent({ className, selectedTrainId, onTrainSelect }) {
  const { data: routesData } = useRoutes();
  const { data: stationsData } = useStations();
  const { positions: wsPositions, isConnected } = useTrainPositions();
  const { data: apiPositions } = useInitialPositions();

  // Use WebSocket if connected, fallback to REST polling
  const trainPositions = useMemo(() => {
    if (isConnected && wsPositions.length > 0) {
      return wsPositions;
    }
    return apiPositions || [];
  }, [isConnected, wsPositions, apiPositions]);

  // Generalization: filter by zoom level
  const visibleStations = useMemo(() => {
    switch (generalization.stationMode) {
      case 'hidden':
        return [];
      case 'major-only':
        return stations.filter((s) => MAJOR_STATIONS.has(s.code));
      default:
        return stations;
    }
  }, [stations, generalization.stationMode]);

  return (
    <MapContainer center={THAILAND_CENTER} zoom={INITIAL_ZOOM}>
      <MapController onBBoxChange={handleBBoxChange} />
      <TileLayer url={activeTopic.tileUrl} />

      {/* Canvas layer for non-selected trains */}
      {!useDomTrains && (
        <CanvasTrainLayer
          positions={canvasTrains}
          selectedTrainId={selectedTrainId}
          onTrainSelect={onTrainSelect}
        />
      )}

      {/* Rich DOM marker for selected train */}
      {selectedTrainPosition && (
        <TrainMarker
          position={selectedTrainPosition}
          isSelected={true}
          onSelect={onTrainSelect}
        />
      )}

      {/* Route highlighting on selection */}
      {visibleRoutes.map((route) => {
        const isHighlighted = selectedTrainPosition?.route_id === route.id;
        return (
          <Polyline
            key={route.id}
            positions={positions}
            weight={isHighlighted ? 7 : 4}
            opacity={isHighlighted ? 1.0 : 0.7}
          />
        );
      })}

      <LayerTree />
    </MapContainer>
  );
}
```

**MapController** — BBOX, Permalink, Zoom Tracking:
```typescript
function MapController({ onBBoxChange }: { onBBoxChange: (bbox: string) => void }) {
  const map = useMap();

  useMapEvents({
    moveend() {
      const center = map.getCenter();
      const zoom = map.getZoom();
      const params = new URLSearchParams(window.location.search);
      params.set('lat', center.lat.toFixed(4));
      params.set('lng', center.lng.toFixed(4));
      params.set('z', String(zoom));
      window.history.replaceState(null, '', `?${params.toString()}`);

      // BBOX filtering for server-side filtering
      const bounds = map.getBounds();
      const bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
      onBBoxChange(bbox);

      setZoom(zoom);
    },
  });

  return null;
}
```

---

## **4. Zustand Store — map-topic-store.ts**

[map-topic-store.ts](frontend/src/lib/stores/map-topic-store.ts#L1-L250)

**State structure:**
```typescript
interface MapTopicState {
  topics: MapTopic[];
  activeTopicKey: string;
  layerOverrides: Map<string, boolean>;
  zoom: number;
  generalization: ZoomGeneralization;

  setActiveTopic: (key: string) => void;
  toggleLayer: (layerKey: string) => void;
  isLayerVisible: (layerKey: string) => boolean;
  getEffectiveLayers: () => MapLayer[];
  getActiveTopic: () => MapTopic;
}

export const useMapTopicStore = create<MapTopicState>((set, get) => ({
  topics: DEFAULT_TOPICS,
  activeTopicKey: 'railway',
  layerOverrides: new Map(),
  zoom: 6,
  generalization: getGeneralizationForZoom(6),

  toggleLayer: (layerKey) => {
    const state = get();
    const overrides = new Map(state.layerOverrides);
    const current = state.isLayerVisible(layerKey);
    overrides.set(layerKey, !current);
    set({ layerOverrides: overrides });
  },

  isLayerVisible: (layerKey) => {
    const state = get();
    const layer = state.topics.find((t) => t.key === state.activeTopicKey)
      ?.layers.find((l) => l.key === layerKey);
    if (!layer) return false;
    const override = state.layerOverrides.get(layerKey);
    const visible = override !== undefined ? override : layer.visible;
    if (layer.minZoom !== undefined && state.zoom < layer.minZoom) return false;
    if (layer.maxZoom !== undefined && state.zoom > layer.maxZoom) return false;
    return visible;
  },
}));
```

---

## **5. Train Position Fetching & Rendering**

### **useTrainPositions Hook**
[hooks/index.ts](frontend/src/lib/hooks/index.ts#L1-L150)

```typescript
export function useTrainPositions(): {
  positions: TrainPositionUpdate[];
  isConnected: boolean;
  error: string | null;
} {
  const [positions, setPositions] = useState<TrainPositionUpdate[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsClientRef = useRef<TrainWebSocketClient | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const client = getWebSocketClient();
    wsClientRef.current = client;

    const unsubscribeConnect = client.onConnect(() => {
      setIsConnected(true);
      setError(null);
    });

    const unsubscribeMessage = client.onMessage((newPositions) => {
      setPositions(newPositions);
    });

    client.connect();

    return () => {
      unsubscribeConnect();
      unsubscribeMessage();
      client.disconnect();
    };
  }, []);

  return { positions, isConnected, error };
}

// Fallback REST API polling (30s interval)
export function useInitialPositions(): UseQueryResult<TrainPositionUpdate[]> {
  return useQuery({
    queryKey: ['train-positions'],
    queryFn: () => trainApi.getAllPositions(),
    refetchInterval: 30000,
    staleTime: 10000,
  });
}
```

### **API Client**
[api/client.ts](frontend/src/lib/api/client.ts#L1-L250)

```typescript
export const trainApi = {
  getAll: async (page = 1, size = 100): Promise<PaginatedResponse<Train>> => {
    return api.get<PaginatedResponse<Train>>('/trains', { params: { page, size } });
  },

  getAllPositions: async (): Promise<TrainPositionUpdate[]> => {
    return api.get<TrainPositionUpdate[]>('/trains/positions');
  },
};
```

---

## **6. Zoom Generalization Rules**

### **map-topics.ts**
[map-topics.ts](frontend/src/lib/map-topics.ts#L1-L150)

```typescript
export const ZOOM_GENERALIZATION: ZoomGeneralization[] = [
  {
    minZoom: 0,
    maxZoom: 5,
    stationMode: 'hidden',
    trainMode: 'canvas-dots',  // Small dots, no animation overhead
    routeMode: 'simplified',
    trainRadius: 3,
  },
  {
    minZoom: 6,
    maxZoom: 7,
    stationMode: 'major-only',
    trainMode: 'canvas-dots',  // Still canvas for performance
    routeMode: 'full',
    trainRadius: 4,
  },
  {
    minZoom: 10,
    maxZoom: 13,
    stationMode: 'all',
    trainMode: 'canvas-markers',  // L.circleMarker on canvas
    routeMode: 'full',
    trainRadius: 6,
  },
  {
    minZoom: 14,
    maxZoom: 20,
    stationMode: 'all',
    trainMode: 'dom-markers',  // Rich DOM markers, popups available
    routeMode: 'full',
    trainRadius: 8,
  },
];
```

---

## **7. Data Flow Summary**

```
WebSocket Connection (ws://localhost:8002/ws/trains)
    ↓
TrainWebSocketClient.onMessage()
    ↓
useTrainPositions() hook → sets state
    ↓
MapContent receives positions
    ↓
Split: selected vs canvas trains
    ↓
TrainMarker (selected) ← rAF animation + DOM interactions
CanvasTrainLayer (others) ← rAF batch interpolation + canvas render
    ↓
Leaflet.setLatLng() updates map markers
```

---

## **Key Implementation Details**

| Feature | Implementation | Pattern |
|---------|----------------|---------|
| **Animation** | rAF + linear interpolation over 1900ms | mobility-toolbox-js |
| **WebSocket** | Singleton client, event-driven handlers, reconnect with exponential backoff | geops |
| **Visibility API** | Pause heartbeat on tab hide, resume on show | geops |
| **BBOX Filtering** | Send `BBOX minLon,minLat,maxLon,maxLat` on moveend | mobility-toolbox-js RealtimeAPI |
| **Delay Coloring** | Green→Yellow→Orange→Red based on minutes | realtimeByDelayStyle |
| **Canvas Rendering** | L.Canvas renderer + L.CircleMarker for 1000+ trains | RealtimeEngine |
| **Generalization** | 5 zoom levels switching stationMode/trainMode/routeMode | motsByZoom |
| **Routing** | URL query params (lat/lng/z/train) for permalink | trafimage-maps |
| **Layer Tree** | Zustand store + topic/layer toggles + opacity control | trafimage-maps |

---

## **Missing/Incomplete**

- **Station search autocomplete** — hook exists (`useStationSearch`) but no UI component
- **Historical playback** — no timeline scrubber
- **Performance metrics** — no Lighthouse/profiling setup
- **E2E tests** — frontend/TESTING_TODO.md lists Cypress TODOs
- **PWA offline tiles** — no service worker for tile caching

This architecture successfully implements geops best practices for real-time railway tracking at scale!