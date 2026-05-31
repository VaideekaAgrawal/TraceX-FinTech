"use client";

import { useEffect, useState } from "react";
import { api, ProfileData } from "@/lib/api";
import { Card, StatCard, Loader, Badge, EmptyState, FilterBar, FilterOption } from "@/components/ui";
import { formatINR } from "@/lib/utils";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface PeerGroupResult {
  account_id: string;
  occupation: string;
  income_bracket: string;
  declared_income: number;
  actual_volume: number;
  peer_mean: number;
  peer_std: number;
  z_score: number;
  peer_count: number;
}

const PROFILE_FILTERS: FilterOption[] = [
  {
    key: "severity",
    label: "Severity",
    type: "select",
    options: [
      { value: "CRITICAL", label: "Critical (>10x)" },
      { value: "HIGH", label: "High (>5x)" },
      { value: "MEDIUM", label: "Medium (>2x)" },
      { value: "LOW", label: "Low (≤2x)" },
    ],
  },
  { key: "accountSearch", label: "Account ID", type: "text", placeholder: "Search account..." },
  { key: "occupation", label: "Occupation", type: "text", placeholder: "Occupation..." },
  { key: "minRatio", label: "Min Ratio", type: "number", placeholder: "Min ratio" },
];

function getSeverity(ratio: number): { label: string; variant: "danger" | "warning" | "info" | "success" } {
  if (ratio > 10) return { label: "CRITICAL", variant: "danger" };
  if (ratio > 5) return { label: "HIGH", variant: "warning" };
  if (ratio > 2) return { label: "MEDIUM", variant: "info" };
  return { label: "LOW", variant: "success" };
}

function getPointColor(ratio: number): string {
  if (ratio > 10) return "#ef4444";
  if (ratio > 5) return "#f97316";
  return "#3b82f6";
}

export default function ProfilePage() {
  const [data, setData] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [peerAccountId, setPeerAccountId] = useState("");
  const [peerData, setPeerData] = useState<PeerGroupResult | null>(null);
  const [peerLoading, setPeerLoading] = useState(false);
  const [mismatchPage, setMismatchPage] = useState(0);
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});
  const MISMATCH_PER_PAGE = 15;

  useEffect(() => {
    api.getProfile().then(setData).finally(() => setLoading(false));
  }, []);

  const handleFilterChange = (key: string, value: string) => {
    setFilterValues((prev) => ({ ...prev, [key]: value }));
    setMismatchPage(0);
  };
  const handleFilterReset = () => { setFilterValues({}); setMismatchPage(0); };

  const handlePeerAnalysis = async () => {
    if (!peerAccountId.trim()) return;
    setPeerLoading(true);
    try {
      const result = await api.getPeerGroup(peerAccountId.trim());
      setPeerData(result as unknown as PeerGroupResult);
    } catch {
      setPeerData(null);
    } finally {
      setPeerLoading(false);
    }
  };

  if (loading) return <Loader />;
  if (!data) return <EmptyState message="Failed to load profile data" />;

  const { scatter_data, mismatches } = data;
  const mismatchCount = mismatches.length;
  const avgRatio =
    scatter_data.length > 0
      ? (scatter_data.reduce((s, d) => s + d.ratio, 0) / scatter_data.length).toFixed(2)
      : "0";

  const sortedMismatches = [...mismatches].sort(
    (a, b) => ((b as Record<string, number>).ratio || 0) - ((a as Record<string, number>).ratio || 0)
  );

  // Color-coded scatter data
  const redPoints = scatter_data.filter((d) => d.ratio > 10);
  const orangePoints = scatter_data.filter((d) => d.ratio > 5 && d.ratio <= 10);
  const bluePoints = scatter_data.filter((d) => d.ratio <= 5);

  return (
    <div className="space-y-6 p-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Profile Analyzer</h1>
        <p className="text-sm text-slate-400 mt-1">
          Income vs transaction volume peer-group analysis
        </p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Total Accounts" value={scatter_data.length} icon="👤" color="blue" />
        <StatCard label="Mismatches Detected" value={mismatchCount} icon="⚠️" color="red" />
        <StatCard label="Avg Volume/Income Ratio" value={avgRatio} icon="📊" color="purple" />
      </div>

      {/* Scatter Plot */}
      <Card>
        <h2 className="text-lg font-semibold text-white mb-4">
          Income vs Transaction Volume
        </h2>
        <p className="text-xs text-slate-400 mb-4">
          <span className="inline-block w-3 h-3 rounded-full bg-red-500 mr-1" /> Ratio &gt; 10
          <span className="inline-block w-3 h-3 rounded-full bg-orange-500 ml-3 mr-1" /> Ratio &gt; 5
          <span className="inline-block w-3 h-3 rounded-full bg-blue-500 ml-3 mr-1" /> Normal
        </p>
        <div className="h-[400px]">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                type="number"
                dataKey="declared_income"
                name="Declared Income"
                scale="log"
                domain={["auto", "auto"]}
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                label={{ value: "Declared Income (₹)", position: "bottom", fill: "#64748b", fontSize: 12 }}
              />
              <YAxis
                type="number"
                dataKey="actual_volume"
                name="Actual Volume"
                scale="log"
                domain={["auto", "auto"]}
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                label={{ value: "Actual Volume (₹)", angle: -90, position: "left", fill: "#64748b", fontSize: 12 }}
              />
              <ZAxis type="number" dataKey="ratio" range={[30, 200]} />
              <Tooltip
                content={({ payload }) => {
                  if (!payload || !payload.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 text-xs">
                      <p className="text-white font-medium">{d.account_id}</p>
                      <p className="text-slate-300">Income: {formatINR(d.declared_income)}</p>
                      <p className="text-slate-300">Volume: {formatINR(d.actual_volume)}</p>
                      <p className="text-slate-300">Occupation: {d.occupation}</p>
                      <p className="font-medium" style={{ color: getPointColor(d.ratio) }}>
                        Ratio: {d.ratio.toFixed(2)}x
                      </p>
                    </div>
                  );
                }}
              />
              <ReferenceLine
                segment={[
                  { x: 10000, y: 10000 },
                  { x: 100000000, y: 100000000 },
                ]}
                stroke="#475569"
                strokeDasharray="5 5"
                label={{ value: "Income = Volume", fill: "#64748b", fontSize: 10 }}
              />
              <Scatter data={bluePoints} fill="#3b82f6" fillOpacity={0.7} />
              <Scatter data={orangePoints} fill="#f97316" fillOpacity={0.8} />
              <Scatter data={redPoints} fill="#ef4444" fillOpacity={0.9} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Mismatches Table */}
      <Card>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h2 className="text-lg font-semibold text-white">
            Income-Volume Mismatches
          </h2>
        </div>
        <FilterBar filters={PROFILE_FILTERS} values={filterValues} onChange={handleFilterChange} onReset={handleFilterReset} />
        {sortedMismatches.length === 0 ? (
          <EmptyState message="No mismatches detected" />
        ) : (
          (() => {
            const filtered = sortedMismatches.filter((m: Record<string, unknown>) => {
              const ratio = (m.ratio as number) || 0;
              const sev = getSeverity(ratio).label;
              if (filterValues.severity && sev !== filterValues.severity) return false;
              if (filterValues.accountSearch && !String(m.account_id || "").toLowerCase().includes(filterValues.accountSearch.toLowerCase())) return false;
              if (filterValues.occupation && !String(m.occupation || "").toLowerCase().includes(filterValues.occupation.toLowerCase())) return false;
              if (filterValues.minRatio && ratio < Number(filterValues.minRatio)) return false;
              return true;
            });
            const totalPages = Math.ceil(filtered.length / MISMATCH_PER_PAGE);
            const paged = filtered.slice(mismatchPage * MISMATCH_PER_PAGE, (mismatchPage + 1) * MISMATCH_PER_PAGE);
            return (
              <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase">
                  <th className="text-left py-3 px-2">Account ID</th>
                  <th className="text-left py-3 px-2">Occupation</th>
                  <th className="text-left py-3 px-2">Income Bracket</th>
                  <th className="text-right py-3 px-2">Declared Income</th>
                  <th className="text-right py-3 px-2">Actual Volume</th>
                  <th className="text-right py-3 px-2">Ratio</th>
                  <th className="text-center py-3 px-2">Severity</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((m: Record<string, unknown>, i) => {
                  const ratio = (m.ratio as number) || 0;
                  const severity = getSeverity(ratio);
                  return (
                    <tr key={i} className="border-b border-slate-800 hover:bg-slate-800/50">
                      <td className="py-2 px-2 text-blue-400 font-mono text-xs">
                        {m.account_id as string}
                      </td>
                      <td className="py-2 px-2 text-slate-300">{m.occupation as string}</td>
                      <td className="py-2 px-2 text-slate-300">{m.income_bracket as string}</td>
                      <td className="py-2 px-2 text-right text-slate-300">
                        {formatINR(m.declared_income as number)}
                      </td>
                      <td className="py-2 px-2 text-right text-slate-300">
                        {formatINR(m.actual_volume as number)}
                      </td>
                      <td className="py-2 px-2 text-right font-medium" style={{ color: getPointColor(ratio) }}>
                        {ratio.toFixed(2)}x
                      </td>
                      <td className="py-2 px-2 text-center">
                        <Badge variant={severity.variant}>{severity.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-800">
              <span className="text-[10px] text-slate-500">{filtered.length} mismatches · Page {mismatchPage + 1} of {totalPages}</span>
              <div className="flex items-center gap-1">
                <button onClick={() => setMismatchPage(Math.max(0, mismatchPage - 1))} disabled={mismatchPage === 0} className="px-2 py-1 text-xs bg-slate-800 text-slate-400 rounded disabled:opacity-30 hover:text-white">←</button>
                <span className="text-[10px] text-slate-500 px-2">{mismatchPage + 1} / {totalPages}</span>
                <button onClick={() => setMismatchPage(Math.min(totalPages - 1, mismatchPage + 1))} disabled={mismatchPage >= totalPages - 1} className="px-2 py-1 text-xs bg-slate-800 text-slate-400 rounded disabled:opacity-30 hover:text-white">→</button>
              </div>
            </div>
          )}
              </>
            );
          })()
        )}
      </Card>

      {/* Peer Group Analysis */}
      <Card>
        <h2 className="text-lg font-semibold text-white mb-4">Peer Group Analysis</h2>
        <div className="flex gap-3 mb-6">
          <input
            type="text"
            value={peerAccountId}
            onChange={(e) => setPeerAccountId(e.target.value)}
            placeholder="Enter Account ID..."
            className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            onKeyDown={(e) => e.key === "Enter" && handlePeerAnalysis()}
          />
          <button
            onClick={handlePeerAnalysis}
            disabled={peerLoading}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {peerLoading ? "Analyzing..." : "Analyze"}
          </button>
        </div>

        {peerLoading && <Loader />}

        {peerData && !peerLoading && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Occupation</p>
                <p className="text-sm text-white font-medium">{peerData.occupation}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Income Bracket</p>
                <p className="text-sm text-white font-medium">{peerData.income_bracket}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Declared Income</p>
                <p className="text-sm text-white font-medium">{formatINR(peerData.declared_income)}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Actual Volume</p>
                <p className="text-sm text-white font-medium">{formatINR(peerData.actual_volume)}</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Peer Mean Volume</p>
                <p className="text-sm text-green-400 font-medium">{formatINR(peerData.peer_mean)}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Peer Std Dev</p>
                <p className="text-sm text-slate-300 font-medium">{formatINR(peerData.peer_std)}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Z-Score</p>
                <p className={`text-sm font-bold ${peerData.z_score > 3 ? "text-red-400" : peerData.z_score > 2 ? "text-orange-400" : "text-green-400"}`}>
                  {peerData.z_score.toFixed(2)}
                </p>
              </div>
            </div>

            {/* Visual comparison bar */}
            <div className="bg-slate-800/50 rounded-lg p-4">
              <p className="text-xs text-slate-400 mb-3">Volume Comparison (Account vs Peer Mean)</p>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 w-24">Account</span>
                  <div className="flex-1 bg-slate-700 rounded-full h-5 overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full flex items-center justify-end pr-2"
                      style={{
                        width: `${Math.min((peerData.actual_volume / Math.max(peerData.actual_volume, peerData.peer_mean)) * 100, 100)}%`,
                      }}
                    >
                      <span className="text-[10px] text-white font-medium">{formatINR(peerData.actual_volume)}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 w-24">Peer Mean</span>
                  <div className="flex-1 bg-slate-700 rounded-full h-5 overflow-hidden">
                    <div
                      className="h-full bg-green-500 rounded-full flex items-center justify-end pr-2"
                      style={{
                        width: `${Math.min((peerData.peer_mean / Math.max(peerData.actual_volume, peerData.peer_mean)) * 100, 100)}%`,
                      }}
                    >
                      <span className="text-[10px] text-white font-medium">{formatINR(peerData.peer_mean)}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
