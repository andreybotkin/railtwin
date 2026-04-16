import type { Trajectory } from './trajectory-interpolation';

export type TrajectoryMessage = {
  type: 'trajectory_delta' | 'keepalive';
  timestamp: number;
  upserts?: Trajectory[];
  removed_ids?: number[];
};

export class TrajectoryWebSocketClient {
  private ws: WebSocket | null = null;

  connect(onMessage: (message: TrajectoryMessage) => void) {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${protocol}://${window.location.host}/ws/trajectory`);
    this.ws.onmessage = (event) => onMessage(JSON.parse(event.data) as TrajectoryMessage);
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}
