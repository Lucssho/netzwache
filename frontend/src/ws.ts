type Handler = (event: string, data: any) => void;

export class LiveStream {
  private ws: WebSocket | null = null;
  private handler: Handler;
  private retry = 0;
  private timer: number | null = null;
  private ping: number | null = null;
  public connected = false;

  constructor(handler: Handler) {
    this.handler = handler;
  }

  connect(): void {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const base = import.meta.env.VITE_WS_BASE ?? `${proto}://${location.host}`;
    try {
      this.ws = new WebSocket(`${base}/ws`);
    } catch {
      this.scheduleRetry();
      return;
    }

    this.ws.onopen = () => {
      this.connected = true;
      this.retry = 0;
      this.handler("__status", { connected: true });
      this.ping = window.setInterval(() => this.ws?.send("ping"), 20000);
    };

    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        this.handler(msg.event, msg.data);
      } catch {
        /* ignore */
      }
    };

    this.ws.onclose = () => {
      this.connected = false;
      this.handler("__status", { connected: false });
      if (this.ping) window.clearInterval(this.ping);
      this.scheduleRetry();
    };

    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleRetry(): void {
    if (this.timer) window.clearTimeout(this.timer);
    const delay = Math.min(15000, 1000 * 2 ** this.retry++);
    this.timer = window.setTimeout(() => this.connect(), delay);
  }
}
