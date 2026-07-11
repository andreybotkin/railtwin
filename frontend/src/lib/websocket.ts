/**
 * Trajectory WebSocket client.
 *
 * Delta-protocol spoken with `gateway /ws/trajectory`:
 *   Server → Client:
 *     {"source":"snapshot","content":[<Trajectory>, ...],"timestamp":<ms>}
 *     {"source":"trajectory","content":<Trajectory>,"timestamp":<ms>}
 *     {"source":"deleted_vehicles","content":<train_id>,"timestamp":<ms>}
 *     {"source":"keepalive","timestamp":<ms>}
 *   Client → Server:
 *     "BBOX minLon,minLat,maxLon,maxLat"   — narrow the stream to the viewport.
 *     "PING"                                — liveness probe.
 *     "RESET"                               — request a full retransmit.
 */

import type { Trajectory } from '@/types';

type TrajectoryWSMessage =
  | { source: 'snapshot'; content: Trajectory[]; timestamp: number }
  | { source: 'trajectory'; content: Trajectory; timestamp: number }
  | { source: 'deleted_vehicles'; content: number; timestamp: number }
  | { source: 'keepalive'; timestamp: number };

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8002';
const HEARTBEAT_INTERVAL_MS = 10_000;
const MAX_RECONNECT_ATTEMPTS = 5;
const INITIAL_RECONNECT_DELAY_MS = 1_000;

type UpdateHandler = (trajectories: Map<number, Trajectory>) => void;

export class TrajectoryWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private shouldReconnect = true;
  private currentBBox: string | null = null;
  private lastSentBBox: string | null = null;
  private visibilityHandler: (() => void) | null = null;
  private notifyFrameId: number | null = null;
  private notifyTimeoutId: ReturnType<typeof setTimeout> | null = null;

  readonly trajectories = new Map<number, Trajectory>();
  private updateHandlers = new Set<UpdateHandler>();

  connect(): void {
    if (
      this.ws?.readyState === WebSocket.OPEN ||
      this.ws?.readyState === WebSocket.CONNECTING
    )
      return;

    this.shouldReconnect = true;
    const bboxAtConnect = this.currentBBox;
    const query = bboxAtConnect
      ? `?bbox=${encodeURIComponent(bboxAtConnect)}`
      : '';

    try {
      this.ws = new WebSocket(`${WS_BASE_URL}/ws/trajectory${query}`);
    } catch {
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.lastSentBBox = bboxAtConnect;
      this.startHeartbeat();
      this.setupVisibilityHandler();

      if (this.currentBBox && this.currentBBox !== bboxAtConnect) {
        this.sendBBox(this.currentBBox);
      }
    };

    this.ws.onmessage = (event) => {
      let msg: TrajectoryWSMessage;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      if (msg.source === 'snapshot') {
        this.trajectories.clear();
        for (const trajectory of msg.content) {
          this.trajectories.set(trajectory.train_id, trajectory);
        }
        this.scheduleNotify();
      } else if (msg.source === 'trajectory') {
        this.trajectories.set(msg.content.train_id, msg.content);
        this.scheduleNotify();
      } else if (msg.source === 'deleted_vehicles') {
        if (this.trajectories.delete(msg.content)) {
          this.scheduleNotify();
        }
      }
    };

    this.ws.onerror = () => {
      /* silent — onclose will decide whether to reconnect */
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      this.lastSentBBox = null;
      if (this.shouldReconnect) this.scheduleReconnect();
    };
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.stopHeartbeat();
    this.teardownVisibilityHandler();
    this.cancelScheduledNotify();
    this.lastSentBBox = null;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.trajectories.clear();
  }

  sendBBox(bbox: string): void {
    this.currentBBox = bbox;
    if (
      this.ws?.readyState === WebSocket.OPEN &&
      bbox !== this.lastSentBBox
    ) {
      this.ws.send(`BBOX ${bbox}`);
      this.lastSentBBox = bbox;
    }
  }

  onUpdate(handler: UpdateHandler): () => void {
    this.updateHandlers.add(handler);
    return () => {
      this.updateHandlers.delete(handler);
    };
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private notifyHandlers(): void {
    const snapshot = new Map(this.trajectories);
    this.updateHandlers.forEach((handler) => handler(snapshot));
  }

  private scheduleNotify(): void {
    if (this.notifyFrameId !== null || this.notifyTimeoutId !== null) return;

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
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return;
    const delay = INITIAL_RECONNECT_DELAY_MS * 2 ** this.reconnectAttempts;
    this.reconnectAttempts += 1;
    setTimeout(() => this.connect(), delay);
  }

  private startHeartbeat(): void {
    if (this.heartbeatInterval) return;
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
    if (typeof document === 'undefined' || this.visibilityHandler) return;
    this.visibilityHandler = () => {
      if (document.hidden) {
        this.stopHeartbeat();
        return;
      }
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.startHeartbeat();
        if (this.currentBBox) this.sendBBox(this.currentBBox);
      } else if (this.shouldReconnect) {
        this.reconnectAttempts = 0;
        this.connect();
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

let singleton: TrajectoryWebSocketClient | null = null;

export function getTrajectoryClient(): TrajectoryWebSocketClient {
  if (!singleton) singleton = new TrajectoryWebSocketClient();
  return singleton;
}
