export interface AgentUpdate {
  agent_id: string;
  hostname: string;
  last_run: number;
  pending: any[];
  history: any[];
  blocked_ips: any[];
  metrics?: any;
}

export interface DashboardState {
  agents: Record<string, AgentUpdate>;
  last_updated: number;
}