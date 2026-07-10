import { DurableObject } from "cloudflare:workers";

export class AgentPulseState extends DurableObject {
  async fetch(request: Request) {
    const url = new URL(request.url);

    if (url.pathname === "/ws") {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);

      server.accept();

      server.addEventListener("message", (event) => {
        this.broadcast(event.data as string);
      });

      return new Response(null, {
        status: 101,
        webSocket: client,
      });
    }

    return new Response("Not found", { status: 404 });
  }

  broadcast(message: string) {
    // TODO: broadcast to all connected clients
    console.log("[DurableObject] broadcast:", message);
  }
}
