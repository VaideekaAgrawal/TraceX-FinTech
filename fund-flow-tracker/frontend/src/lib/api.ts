const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Types ──────────────────────────────────────────────────────────────────
export interface OverviewData {
  stats: { num_nodes: number; num_edges: number; num_components: number; density: number; avg_in_degree: number; avg_out_degree: number };
  risk_distribution: Record<string, number>;
  role_distribution: Record<string, number>;
  top_alerts: Alert[];
  pattern_counts: Record<string, number>;
  total_flagged: number;
  total_anomalies: number;
  fraud_metrics: Record<string, number | number[]>;
  total_amount: number;
  avg_risk: number;
}

export interface Alert {
  account_id: string;
  risk_score: number;
  risk_level: string;
  risk_color: string;
  role: string;
  branch_city: string;
  account_type: string;
}

export interface Account {
  account_id: string;
  account_type: string;
  branch_city: string;
  occupation: string;
  income_bracket: string;
  declared_annual_income: number;
  total_in_flow: number;
  total_out_flow: number;
  txn_count: number;
  risk_score: number;
  risk_level: string;
  risk_color: string;
  role: string;
  role_confidence: number;
  anomaly_score: number;
}

export interface AccountDetail {
  account: Record<string, string | number>;
  risk_score: number;
  risk_level: string;
  risk_color: string;
  role: string;
  role_confidence: number;
  anomaly_score: number;
  fraud_probability: number;
  features: Record<string, number>;
  confidence: { level: string; count: number; indicators: string[] };
  priority: string;
  total_amount: number;
  counterparties: number;
  recent_transactions: Transaction[];
}

export interface Transaction {
  txn_id: string;
  timestamp: string;
  source_account: string;
  dest_account: string;
  amount: number;
  channel: string;
  txn_type?: string;
  is_laundering: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center?: string;
}

export interface GraphNode {
  id: string;
  risk_score: number;
  risk_level: string;
  risk_color: string;
  role: string;
  is_center?: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  amount: number;
  channel: string;
  timestamp: string;
}

export interface AnomalyData {
  anomaly_scores: { account_id: string; anomaly_score: number }[];
  feature_importance: Record<string, number>;
  investigation_queue: InvestigationItem[];
  speed_alerts: SpeedAlert[];
}

export interface InvestigationItem {
  account_id: string;
  risk_score: number;
  risk_level: string;
  risk_color: string;
  role: string;
  priority: string;
  confidence_level: string;
  confidence_count: number;
  indicators: string[];
  anomaly_score: number;
  fraud_probability: number;
  total_amount: number;
  branch_city: string;
}

export interface SpeedAlert {
  accounts: string[];
  category: string;
  label: string;
  color: string;
  avg_minutes_per_hop: number;
  total_minutes: number;
  hops: number;
  total_amount: number;
}

export interface PatternData {
  patterns: Record<string, unknown>;
  flagged_accounts: string[];
}

export interface ProfileData {
  scatter_data: { account_id: string; declared_income: number; actual_volume: number; occupation: string; income_bracket: string; ratio: number }[];
  mismatches: Record<string, unknown>[];
}

export interface ChannelData {
  summary: { channel: string; count: number; total_amount: number; avg_amount: number; max_amount: number }[];
  sankey: { source_type: string; channel: string; dest_type: string; count: number; total: number }[];
  heatmap: { channel: string; hour: number; count: number }[];
  suspicious: { channel: string; count: number; total: number; unique_accounts: number }[];
}

export interface FundTrailResult {
  account_id?: string;
  component_size?: number;
  trail_count?: number;
  trails?: Record<string, unknown>[][];
  error?: string;
}

export interface AccompliceResult {
  start_node: string;
  accomplices: { account_id: string; visit_probability: number; risk_score: number; risk_level: string; role: string }[];
}

export interface EvidenceResult {
  case_id: string;
  summary: Record<string, unknown>;
  pdf_base64: string;
  json_data: string;
}

// ── API Functions ──────────────────────────────────────────────────────────
export const api = {
  getOverview: () => fetchApi<OverviewData>("/api/overview"),
  getAccounts: () => fetchApi<Account[]>("/api/accounts"),
  getAccountDetail: (id: string) => fetchApi<AccountDetail>(`/api/accounts/${id}`),
  getGraph: (maxNodes = 100) => fetchApi<GraphData>(`/api/graph?max_nodes=${maxNodes}`),
  getEgoGraph: (id: string, radius = 2) => fetchApi<GraphData>(`/api/graph/ego/${id}?radius=${radius}`),
  getFundTrail: (account_id: string, direction = "both", max_depth = 5) =>
    fetchApi<FundTrailResult>("/api/graph/fund-trail", { method: "POST", body: JSON.stringify({ account_id, direction, max_depth }) }),
  getRandomWalk: (start_node: string) =>
    fetchApi<AccompliceResult>("/api/graph/random-walk", { method: "POST", body: JSON.stringify({ start_node }) }),
  getAnomaly: () => fetchApi<AnomalyData>("/api/anomaly"),
  getPatterns: () => fetchApi<PatternData>("/api/patterns"),
  getFirstSuspicious: (id: string) => fetchApi<{ found: boolean; data?: Record<string, unknown> }>(`/api/patterns/first-suspicious/${id}`),
  getProfile: () => fetchApi<ProfileData>("/api/profile"),
  getPeerGroup: (id: string) => fetchApi<Record<string, unknown>>(`/api/profile/${id}`),
  getChannels: () => fetchApi<ChannelData>("/api/channels"),
  generateEvidence: (case_id: string, account_ids: string[], pattern_type: string, case_notes: string) =>
    fetchApi<EvidenceResult>("/api/evidence/generate", { method: "POST", body: JSON.stringify({ case_id, account_ids, pattern_type, case_notes }) }),
  getTransactions: (limit = 100, offset = 0) =>
    fetchApi<{ total: number; transactions: Transaction[] }>(`/api/transactions?limit=${limit}&offset=${offset}`),
  getHealth: () => fetchApi<{ status: string; initialized: boolean; accounts: number; transactions: number }>("/api/health"),
};
