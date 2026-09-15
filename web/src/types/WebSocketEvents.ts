export interface QuoteUpdateEvent {
  type: 'QUOTE_UPDATE';
  symbol: string;
  price: number;
  bid: number;
  ask: number;
  volume: number;
  timestamp: string;
}

export interface OrderStreamEvent {
  type: 'ORDER_UPDATE';
  order_id: string;
  symbol: string;
  status: 'PENDING' | 'FILLED' | 'CANCELLED' | 'REJECTED';
  filled_quantity: number;
  avg_price: number;
  timestamp: string;
}

export interface TelemetrySignalEvent {
  type: 'TELEMETRY_SIGNAL';
  signal_id: string;
  strategy: string;
  symbol: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  timestamp: string;
}

export interface SystemStatusEvent {
  type: 'SYSTEM_STATUS';
  status: 'OPERATIONAL' | 'DEGRADED' | 'MAINTENANCE';
  active_connections: number;
  timestamp: string;
}

export type WebSocketEvent =
  | QuoteUpdateEvent
  | OrderStreamEvent
  | TelemetrySignalEvent
  | SystemStatusEvent;
