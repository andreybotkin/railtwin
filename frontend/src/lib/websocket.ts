/**
 * WebSocket clients for real-time train position and trajectory updates.
 *
 * Best practices from geops/mobility-toolbox-js:
 * - Visibility API: pause WS when tab is hidden, resume on return
 * - BBOX command: send visible map bounds for server-side filtering
 * - Ping/keepalive with exponential backoff reconnect
 *
 * Two clients available:
 * - TrainWebSocketClient (/ws/trains) — position snapshots every N seconds
 * - TrajectoryWebSocketClient (/ws/trajectory) — geops time_intervals for smooth animation
 */

import type { WebSocketMessage, TrainPositionUpdate, TrainTrajectory, TrajectoryWSMessage } from '@/types';

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8002';

// Heartbeat interval in milliseconds (slightly less than server timeout)
const HEARTBEAT_INTERVAL_MS = 10000;

type MessageHandler = (positions: TrainPositionUpdate[]) => void;
type ErrorHandler = (error: Event) => void;
type ConnectionHandler = () => void;
type Unsubscribe = () => void;

/**
 * WebSocket client for train position updates.
 */
export class TrainWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private shouldReconnect = true;
  private currentBBox: string | null = null;
  private visibilityHandler: (() => void) | null = null;

  private onMessageHandlers = new Set<MessageHandler>();
  private onErrorHandlers = new Set<ErrorHandler>();
  private onConnectHandlers = new Set<ConnectionHandler>();
  private onDisconnectHandlers = new Set<ConnectionHandler>();

  /**
   * Connect to the WebSocket server.
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.shouldReconnect = true;

    try {
      this.ws = new WebSocket(`${WS_BASE_URL}/ws/trains`);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.setupVisibilityHandler();
        this.onConnectHandlers.forEach((handler) => {
          handler();
        });
        // Re-send BBOX on reconnect
        if (this.currentBBox) {
          this.sendBBox(this.currentBBox);
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          if (message.type === 'positions' && Array.isArray(message.data)) {
            this.onMessageHandlers.forEach((handler) => {
              handler(message.data as TrainPositionUpdate[]);
            });
          }
          // Ignore keepalive messages silently
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.onErrorHandlers.forEach((handler) => {
          handler(error);
        });
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.stopHeartbeat();
        this.onDisconnectHandlers.forEach((handler) => {
          handler();
        });

        if (this.shouldReconnect) {
          this.attemptReconnect();
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
    }
  }

  /**
   * Disconnect from the WebSocket server.
   */
  disconnect(): void {
    this.shouldReconnect = false;
    this.stopHeartbeat();
    this.teardownVisibilityHandler();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * Send BBOX to server for viewport-based filtering.
   * Pattern from mobility-toolbox-js RealtimeAPI: "BBOX minLon,minLat,maxLon,maxLat"
   */
  sendBBox(bbox: string): void {
    this.currentBBox = bbox;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(`BBOX ${bbox}`);
    }
  }

  /**
   * Attempt to reconnect with exponential backoff.
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnection attempts reached');
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * Start heartbeat to keep connection alive.
   */
  private startHeartbeat(): void {
    if (this.heartbeatInterval) {
      return;
    }
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  /**
   * Stop heartbeat.
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Setup Visibility API handler to pause/resume WS when tab is hidden/shown.
   * Pattern from mobility-toolbox-js RealtimeEngine.onDocumentVisibilityChange().
   */
  private setupVisibilityHandler(): void {
    if (typeof document === 'undefined') return;

    this.visibilityHandler = () => {
      if (document.hidden) {
        // Tab hidden — pause heartbeat to save resources
        this.stopHeartbeat();
      } else {
        // Tab visible again — restart heartbeat and reconnect if needed
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.startHeartbeat();
          // Re-send BBOX to get fresh data for current viewport
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

  /**
   * Teardown Visibility API handler.
   */
  private teardownVisibilityHandler(): void {
    if (this.visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.visibilityHandler);
      this.visibilityHandler = null;
    }
  }

  /**
   * Register message handler.
   */
  onMessage(handler: MessageHandler): Unsubscribe {
    this.onMessageHandlers.add(handler);
    return () => {
      this.onMessageHandlers.delete(handler);
    };
  }

  /**
   * Register error handler.
   */
  onError(handler: ErrorHandler): Unsubscribe {
    this.onErrorHandlers.add(handler);
    return () => {
      this.onErrorHandlers.delete(handler);
    };
  }

  /**
   * Register connect handler.
   */
  onConnect(handler: ConnectionHandler): Unsubscribe {
    this.onConnectHandlers.add(handler);
    return () => {
      this.onConnectHandlers.delete(handler);
    };
  }

  /**
   * Register disconnect handler.
   */
  onDisconnect(handler: ConnectionHandler): Unsubscribe {
    this.onDisconnectHandlers.add(handler);
    return () => {
      this.onDisconnectHandlers.delete(handler);
    };
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton instance
let wsClient: TrainWebSocketClient | null = null;

/**
 * Get singleton WebSocket client instance.
 */
export function getWebSocketClient(): TrainWebSocketClient {
  if (!wsClient) {
    wsClient = new TrainWebSocketClient();
  }
  return wsClient;
}

// ---------------------------------------------------------------------------
// TrajectoryWebSocketClient — geops mobility-toolbox-js RealtimeEngine pattern
// Connects to /ws/trajectory and maintains a Map<trainId, TrainTrajectory>.
// Uses time_intervals for frame-accurate position interpolation without polling.
// ---------------------------------------------------------------------------

type TrajectoryUpdateHandler = (trajectories: Map<number, TrainTrajectory>) => void;

/**
 * WebSocket client for geops-compatible trajectory data.
 *
 * Protocol (mirrors geops WebSocketAPI / RealtimeEngine):
 *   Server → Client:
 *     {"source":"trajectory","content":<trajectory>,"timestamp":<ms>}
 *     {"source":"deleted_vehicles","content":<train_id>,"timestamp":<ms>}
 *   Client → Server:
 *     BBOX minLon,minLat,maxLon,maxLat
 *     PING
 *     RESET
 *
 * TODO (deferred, see geops RealtimeEngine):
 *   - Subscribe/unsubscribe individual vehicle channels (GET/SUB/DEL)
 *   - permessage-deflate compression for large payloads
 */
export class TrajectoryWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private shouldReconnect = true;
  private currentBBox: string | null = null;
  private visibilityHandler: (() => void) | null = null;
  private notifyFrameId: number | null = null;
  private notifyTimeoutId: ReturnType<typeof setTimeout> | null = null;

  /** In-memory trajectory dictionary — mirrors geops client-side state */
  readonly trajectories = new Map<number, TrainTrajectory>();

  private updateHandlers = new Set<TrajectoryUpdateHandler>();

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.shouldReconnect = true;

    try {
      this.ws = new WebSocket(`${WS_BASE_URL}/ws/trajectory`);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.setupVisibilityHandler();
        if (this.currentBBox) {
          this.ws!.send(`BBOX ${this.currentBBox}`);
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const msg: TrajectoryWSMessage = JSON.parse(event.data);
          if (msg.source === 'trajectory') {
            const t = msg.content;
            this.trajectories.set(t.properties.train_id, t);
            this.scheduleNotify();
          } else if (msg.source === 'deleted_vehicles') {
            this.trajectories.delete(msg.content);
            this.scheduleNotify();
          }
          // keepalive: ignore silently
        } catch {
          // Malformed message — ignore
        }
      };

      this.ws.onerror = () => { /* silent */ };

      this.ws.onclose = () => {
        this.stopHeartbeat();
        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      };
    } catch {
      // WS constructor can throw in SSR context
    }
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.stopHeartbeat();
    this.teardownVisibilityHandler();
    this.cancelScheduledNotify();
    if (this.ws) { this.ws.close(); this.ws = null; }
    this.trajectories.clear();
  }

  sendBBox(bbox: string): void {
    this.currentBBox = bbox;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(`BBOX ${bbox}`);
    }
  }

  /** Register a callback that receives the full trajectory map on any change. */
  onUpdate(handler: TrajectoryUpdateHandler): () => void {
    this.updateHandlers.add(handler);
    return () => { this.updateHandlers.delete(handler); };
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private notifyHandlers(): void {
    const snap = new Map(this.trajectories);
    this.updateHandlers.forEach((h) => h(snap));
  }

  private scheduleNotify(): void {
    if (this.notifyFrameId !== null || this.notifyTimeoutId !== null) {
      return;
    }

    if (typeof window === 'undefined' || document.hidden) {
      this.notifyTimeoutId = setTimeout(() => {
        this.notifyTimeoutId = null;
        this.notifyHandlers();
      }, 50);
      return;
    }

    this.notifyFrameId = window.requestAnimationFrame(() => {
      this.notifyFrameId = null;
      this.notifyHandlers();
    });
  }

  private cancelScheduledNotify(): void {
    if (this.notifyFrameId !== null && typeof window !== 'undefined') {
      window.cancelAnimationFrame(this.notifyFrameId);
      this.notifyFrameId = null;
    }
    if (this.notifyTimeoutId !== null) {
      clearTimeout(this.notifyTimeoutId);
      this.notifyTimeoutId = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts++);
    setTimeout(() => this.connect(), delay);
  }

  private startHeartbeat(): void {
    if (this.heartbeatInterval) {
      return;
    }
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send('PING');
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private setupVisibilityHandler(): void {
    if (typeof document === 'undefined') return;
    this.visibilityHandler = () => {
      if (document.hidden) {
        this.stopHeartbeat();
      } else {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.startHeartbeat();
          if (this.currentBBox) this.ws.send(`BBOX ${this.currentBBox}`);
        } else if (this.shouldReconnect) {
          this.reconnectAttempts = 0;
          this.connect();
        }
      }
    };
    document.addEventListener('visibilitychange', this.visibilityHandler);
  }

  private teardownVisibilityHandler(): void {
    if (this.visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.visibilityHandler);
      this.visibilityHandler = null;
    }
  }
}

// Singleton trajectory client
let trajectoryClient: TrajectoryWebSocketClient | null = null;

export function getTrajectoryClient(): TrajectoryWebSocketClient {
  if (!trajectoryClient) {
    trajectoryClient = new TrajectoryWebSocketClient();
  }
  return trajectoryClient;
}
