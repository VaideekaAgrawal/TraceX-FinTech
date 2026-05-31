"use client";

import { useEffect, useState } from "react";
import { api, AnomalyData } from "@/lib/api";
import { Card, StatCard, Loader, Badge } from "@/components/ui";
import { formatINR, getRiskBg, getPriorityColor, getRoleIcon } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
} from "recharts";

export default function AnomalyPage() {
  const [data, setData] = useState<AnomalyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [queuePage, setQueuePage] = useState(0);
  const [queueFilter, setQueueFilter] = useState("");
  const [queuePriorityFilter, setQueuePriorityFilter] = useState<string>("ALL");
  const QUEUE_PER_PAGE = 15;

  useEffect(() => {
    api
      .getAnomaly()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader />;
  if (!data) return <p className="text-slate-400 p-8">Failed to load anomaly data.</p>;

  // Stats
  const queue = data.investigation_queue || [];
  const scores = data.anomaly_scores || [];
  const speedAlerts = data.speed_alerts || [];
  const featureImportance = data.feature_importance || {};

  const totalQueue = queue.length;
  const p1Count = queue.filter((i) => i.priority === "P1").length;
  const p2Count = queue.filter((i) => i.priority === "P2").length;
  const speedAlertCount = speedAlerts.length;

  // Histogram bins
  const bins = Array.from({ length: 10 }, (_, i) => ({
    range: `${i * 10}-${(i + 1) * 10}`,
    count: 0,
    high: i >= 7,
  }));
  scores.forEach(({ anomaly_score }) => {
    const idx = Math.min(Math.floor(anomaly_score / 10), 9);
    bins[idx].count++;
  });

  // Feature importance - top 15
  const featureData = Object.entries(featureImportance)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([name, importance]) => ({ name, importance: +importance.toFixed(4) }));

  // Investigation queue sorted
  const priorityOrder: Record<string, number> = { P1: 0, P2: 1, P3: 2, P4: 3 };
  const sortedQueue = [...queue].sort((a, b) => {
    const pd = (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9);
    if (pd !== 0) return pd;
    return b.risk_score - a.risk_score;
  });

  // Speed alert colors
  const speedCategoryColor = (cat: string) => {
    switch (cat) {
      case "ABNORMAL":
        return "border-red-500/50 bg-red-500/10";
      case "VERY_FAST":
        return "border-orange-500/50 bg-orange-500/10";
      case "FAST":
        return "border-yellow-500/50 bg-yellow-500/10";
      default:
        return "border-slate-700/50 bg-slate-800";
    }
  };

  const featureColors = [
    "#6366f1", "#7c3aed", "#8b5cf6", "#a78bfa", "#6366f1",
    "#7c3aed", "#818cf8", "#a78bfa", "#6366f1", "#7c3aed",
    "#8b5cf6", "#a78bfa", "#818cf8", "#6366f1", "#7c3aed",
  ];

  return (
    <div className="min-h-screen bg-[#0b1120] p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Anomaly Detection</h1>
        <p className="text-sm text-slate-400 mt-1">
          ML-powered fraud detection &amp; investigation queue
        </p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total in Queue" value={totalQueue} icon="📋" color="blue" />
        <StatCard label="P1 Critical" value={p1Count} icon="🚨" color="red" />
        <StatCard label="P2 High" value={p2Count} icon="⚠️" color="orange" />
        <StatCard label="Speed Alerts" value={speedAlertCount} icon="⚡" color="yellow" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Anomaly Score Distribution */}
        <Card>
          <h3 className="text-sm font-semibold text-slate-300 mb-4">
            Anomaly Score Distribution
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={bins}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="range" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                labelStyle={{ color: "#e2e8f0" }}
                itemStyle={{ color: "#e2e8f0" }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {bins.map((entry, idx) => (
                  <Cell key={idx} fill={entry.high ? "#ef4444" : "#3b82f6"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        {/* Feature Importance */}
        <Card>
          <h3 className="text-sm font-semibold text-slate-300 mb-4">
            Feature Importance (Top 15)
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={featureData} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
              <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#94a3b8", fontSize: 10 }}
                width={75}
              />
              <Tooltip
                contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                labelStyle={{ color: "#e2e8f0" }}
                itemStyle={{ color: "#e2e8f0" }}
              />
              <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                {featureData.map((_, idx) => (
                  <Cell key={idx} fill={featureColors[idx % featureColors.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Investigation Priority Queue */}
      <Card>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h3 className="text-sm font-semibold text-slate-300">
            Investigation Priority Queue
          </h3>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="text"
              value={queueFilter}
              onChange={(e) => { setQueueFilter(e.target.value); setQueuePage(0); }}
              placeholder="Filter by Account ID..."
              className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 w-48"
            />
            <div className="flex items-center gap-1">
              {["ALL", "P1", "P2", "P3", "P4"].map((p) => (
                <button
                  key={p}
                  onClick={() => { setQueuePriorityFilter(p); setQueuePage(0); }}
                  className={`px-2 py-1 text-[10px] rounded-full font-medium transition ${
                    queuePriorityFilter === p ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-400 hover:text-white"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>
        {(() => {
          const filtered = sortedQueue
            .filter((item) => queuePriorityFilter === "ALL" || item.priority === queuePriorityFilter)
            .filter((item) => !queueFilter || item.account_id.toLowerCase().includes(queueFilter.toLowerCase()));
          const totalPages = Math.ceil(filtered.length / QUEUE_PER_PAGE);
          const paged = filtered.slice(queuePage * QUEUE_PER_PAGE, (queuePage + 1) * QUEUE_PER_PAGE);
          return (
            <>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 text-left text-xs text-slate-400 uppercase tracking-wider">
                <th className="pb-3 pr-3">Priority</th>
                <th className="pb-3 pr-3">Account ID</th>
                <th className="pb-3 pr-3">Risk Score</th>
                <th className="pb-3 pr-3">Confidence</th>
                <th className="pb-3 pr-3">Role</th>
                <th className="pb-3 pr-3">Anomaly</th>
                <th className="pb-3 pr-3">Fraud Prob</th>
                <th className="pb-3 pr-3">Total Amount</th>
                <th className="pb-3">City</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((item) => (
                <tr
                  key={item.account_id}
                  className="border-b border-slate-700/30 hover:bg-slate-800/50 transition-colors"
                >
                  <td className="py-3 pr-3">
                    <span
                      className={`inline-flex items-center justify-center rounded px-2 py-0.5 text-xs font-bold ${getPriorityColor(item.priority)}`}
                    >
                      {item.priority}
                    </span>
                  </td>
                  <td className="py-3 pr-3">
                    <a
                      href={`/graph?account=${item.account_id}`}
                      className="text-blue-400 hover:text-blue-300 font-mono text-xs"
                    >
                      {item.account_id}
                    </a>
                  </td>
                  <td className="py-3 pr-3">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-2 rounded-full bg-slate-700 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-yellow-500 to-red-500"
                          style={{ width: `${item.risk_score}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-300">{item.risk_score.toFixed(1)}</span>
                    </div>
                  </td>
                  <td className="py-3 pr-3 text-xs text-slate-300">
                    {item.confidence_level} ({item.confidence_count})
                  </td>
                  <td className="py-3 pr-3 text-xs">
                    <span className="mr-1">{getRoleIcon(item.role)}</span>
                    <span className="text-slate-300">{item.role}</span>
                  </td>
                  <td className="py-3 pr-3 text-xs text-slate-300">
                    {item.anomaly_score.toFixed(2)}
                  </td>
                  <td className="py-3 pr-3 text-xs text-slate-300">
                    {(item.fraud_probability * 100).toFixed(1)}%
                  </td>
                  <td className="py-3 pr-3 text-xs text-slate-300">
                    {formatINR(item.total_amount)}
                  </td>
                  <td className="py-3 text-xs text-slate-400">{item.branch_city}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-800">
            <span className="text-[10px] text-slate-500">{filtered.length} items · Page {queuePage + 1} of {totalPages}</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setQueuePage(Math.max(0, queuePage - 1))} disabled={queuePage === 0} className="px-2 py-1 text-xs bg-slate-800 text-slate-400 rounded disabled:opacity-30 hover:text-white">←</button>
              <span className="text-[10px] text-slate-500 px-2">{queuePage + 1} / {totalPages}</span>
              <button onClick={() => setQueuePage(Math.min(totalPages - 1, queuePage + 1))} disabled={queuePage >= totalPages - 1} className="px-2 py-1 text-xs bg-slate-800 text-slate-400 rounded disabled:opacity-30 hover:text-white">→</button>
            </div>
          </div>
        )}
            </>
          );
        })()}
      </Card>

      {/* Speed Alerts */}
      <div>
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Speed Alerts</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {speedAlerts.map((alert, idx) => (
            <div
              key={idx}
              className={`rounded-xl border p-4 ${speedCategoryColor(alert.category)}`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  {alert.label}
                </span>
                <Badge
                  variant={
                    alert.category === "ABNORMAL"
                      ? "danger"
                      : alert.category === "VERY_FAST"
                      ? "warning"
                      : "info"
                  }
                >
                  {alert.category}
                </Badge>
              </div>
              <div className="space-y-1.5 text-xs text-slate-300">
                <div className="flex justify-between">
                  <span className="text-slate-400">Avg min/hop</span>
                  <span className="font-medium">{alert.avg_minutes_per_hop.toFixed(1)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Total Amount</span>
                  <span className="font-medium">{formatINR(alert.total_amount)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Hops</span>
                  <span className="font-medium">{alert.hops}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Accounts</span>
                  <span className="font-medium">{alert.accounts.length}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
