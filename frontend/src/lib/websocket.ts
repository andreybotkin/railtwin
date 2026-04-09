/**
 * WebSocket client for real-time train position updates.
 */

import type { WebSocketMessage, TrainPositionUpdate } from '@/types';

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

// Heartbeat interval in milliseconds (slightly less than server timeout)
const HEARTBEAT_INTERVAL_MS = 25000;

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
        this.onConnectHandlers.forEach((handler) => {
          handler();
        });
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          if (message.type === 'positions' && Array.isArray(message.data)) {
            this.onMessageHandlers.forEach((handler) => {
              handler(message.data as TrainPositionUpdate[]);
            });
          }
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
    if (this.ws) {
      this.ws.close();
      this.ws = null;
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
