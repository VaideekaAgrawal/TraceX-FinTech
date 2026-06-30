"use client";

import { useState, useEffect, Fragment } from "react";
import Link from "next/link";
import { api, InvestigationCase } from "@/lib/api";
import { Card, StatCard, Badge, Loader } from "@/components/ui";

// ── helpers ────────────────────────────────────────────────────────────────

function getMaxRisk(riskScores: Record<string, number>): number {
  const scores = Object.values(riskScores);
  return scores.length > 0 ? Math.max(...scores) : 0;
}

function toRiskLevel(score: number): string {
  if (score >= 76) return "CRITICAL";
  if (score >= 51) return "HIGH";
  if (score >= 26) return "MEDIUM";
  return "LOW";
}

function riskBadgeVariant(
  level: string
): "danger" | "warning" | "success" | "info" | "default" {
  if (level === "CRITICAL") return "danger";
  if (level === "HIGH" || level === "MEDIUM") return "warning";
  if (level === "LOW") return "success";
  return "default";
}

function statusBadge(status: string) {
  switch (status) {
    case "open":
      return <Badge variant="info">Open</Badge>;
    case "in_progress":
      return <Badge variant="warning">In Progress</Badge>;
    case "escalated":
      return <Badge variant="danger">Escalated</Badge>;
    case "closed":
      return <Badge variant="success">Closed</Badge>;
    default:
      return <Badge>{status}</Badge>;
  }
}

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtDateTime(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ── component ──────────────────────────────────────────────────────────────

export default function CasesPage() {
  const [cases, setCases] = useState<InvestigationCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Per-case inline-update state
  const [pendingStatus, setPendingStatus] = useState<Record<string, string>>({});
  const [pendingNotes, setPendingNotes] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const loadCases = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getCases();
      setCases(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load cases");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCases();
  }, []);

  const handleUpdate = async (caseId: string, currentStatus: string) => {
    const status = pendingStatus[caseId] ?? currentStatus;
    const notes = pendingNotes[caseId] ?? "";
    setSaving(caseId);
    try {
      await api.updateCaseStatus(caseId, status, notes);
      await loadCases();
      // Clear pending state for this case
      setPendingStatus((p) => { const n = { ...p }; delete n[caseId]; return n; });
      setPendingNotes((p) => { const n = { ...p }; delete n[caseId]; return n; });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setSaving(null);
    }
  };

  // ── stats ──────────────────────────────────────────────────────────────
  const countByStatus = (s: string) => cases.filter((c) => c.status === s).length;

  // ── render ─────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <main className="min-h-screen bg-[#0a0f1e] pt-16">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <Loader />
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] pt-16">
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Case Management</h1>
            <p className="text-sm text-slate-400 mt-1">
              Track and escalate AML investigation cases
            </p>
          </div>
          <button
            disabled
            className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600/30 text-blue-400 border border-blue-500/30 cursor-not-allowed opacity-60"
            title="Create cases by escalating accounts from the Graph or Anomaly page"
          >
            + New Case
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Stat row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Open"
            value={countByStatus("open")}
            icon="🔵"
            color="blue"
            sub="Awaiting assignment"
          />
          <StatCard
            label="In Progress"
            value={countByStatus("in_progress")}
            icon="🟡"
            color="yellow"
            sub="Under investigation"
          />
          <StatCard
            label="Escalated"
            value={countByStatus("escalated")}
            icon="🔴"
            color="red"
            sub="Requires action"
          />
          <StatCard
            label="Closed"
            value={countByStatus("closed")}
            icon="🟢"
            color="green"
            sub="Resolved"
          />
        </div>

        {/* Cases table */}
        <Card>
          {cases.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <span className="text-4xl mb-3">📂</span>
              <p className="text-slate-300 text-sm font-medium">
                No investigation cases yet.
              </p>
              <p className="text-slate-500 text-xs mt-2 max-w-sm">
                Escalate suspicious accounts from the Graph page or Anomaly queue
                to create cases.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/50">
                    {[
                      "Case ID",
                      "Accounts",
                      "Pattern",
                      "Risk Level",
                      "Investigator",
                      "Status",
                      "Created",
                      "Actions",
                    ].map((h) => (
                      <th
                        key={h}
                        className="text-left py-3 px-4 text-xs font-medium text-slate-400 uppercase tracking-wider"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {cases.map((c) => {
                    const maxRisk = getMaxRisk(c.risk_scores);
                    const riskLevel = toRiskLevel(maxRisk);
                    const isExpanded = expandedId === c.case_id;
                    const currentStatus = pendingStatus[c.case_id] ?? c.status;

                    return (
                      <Fragment key={c.case_id}>
                        {/* Summary row */}
                        <tr
                          className="hover:bg-slate-800/30 cursor-pointer transition-colors"
                          onClick={() =>
                            setExpandedId(isExpanded ? null : c.case_id)
                          }
                        >
                          <td className="py-3 px-4 font-mono text-xs text-blue-400 whitespace-nowrap">
                            {c.case_id}
                          </td>
                          <td className="py-3 px-4 text-slate-300">
                            {c.account_ids.length}
                          </td>
                          <td className="py-3 px-4 text-slate-300 capitalize whitespace-nowrap">
                            {c.pattern_type.replace(/_/g, " ")}
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant={riskBadgeVariant(riskLevel)}>
                              {riskLevel}
                              {maxRisk > 0 && (
                                <span className="ml-1 opacity-70">
                                  ({maxRisk.toFixed(0)})
                                </span>
                              )}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-slate-400 text-xs">
                            {c.investigator}
                          </td>
                          <td className="py-3 px-4">{statusBadge(c.status)}</td>
                          <td className="py-3 px-4 text-slate-500 text-xs whitespace-nowrap">
                            {fmtDate(c.created_at)}
                          </td>
                          <td className="py-3 px-4">
                            <button
                              className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedId(isExpanded ? null : c.case_id);
                              }}
                            >
                              {isExpanded ? "Collapse ▲" : "Details ▼"}
                            </button>
                          </td>
                        </tr>

                        {/* Expanded detail panel */}
                        {isExpanded && (
                          <tr>
                            <td
                              colSpan={8}
                              className="px-6 py-5 bg-slate-900/60 border-b border-slate-700/50"
                            >
                              <div className="space-y-5">
                                {/* Account chips */}
                                <div>
                                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                                    Account IDs
                                  </p>
                                  <div className="flex flex-wrap gap-2">
                                    {c.account_ids.map((accId) => (
                                      <Link
                                        key={accId}
                                        href={`/graph?account=${accId}`}
                                        className="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs font-mono hover:bg-blue-500/20 transition-colors"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        {accId}
                                      </Link>
                                    ))}
                                  </div>
                                </div>

                                {/* STR reference */}
                                {c.str_reference && (
                                  <div>
                                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                                      STR Reference
                                    </p>
                                    <p className="text-xs text-slate-300 font-mono">
                                      {c.str_reference}
                                    </p>
                                  </div>
                                )}

                                {/* Notes */}
                                {c.notes && (
                                  <div>
                                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                                      Notes
                                    </p>
                                    <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                                      {c.notes}
                                    </p>
                                  </div>
                                )}

                                {/* Timeline */}
                                <div>
                                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                                    Timeline
                                  </p>
                                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                                    <span>
                                      Created:{" "}
                                      <span className="text-slate-400">
                                        {fmtDateTime(c.created_at)}
                                      </span>
                                    </span>
                                    <span className="text-slate-600">→</span>
                                    <span>
                                      Last updated:{" "}
                                      <span className="text-slate-400">
                                        {fmtDateTime(c.updated_at)}
                                      </span>
                                    </span>
                                  </div>
                                </div>

                                {/* Inline status update */}
                                <div
                                  className="flex flex-wrap items-center gap-3 pt-3 border-t border-slate-700/50"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <select
                                    value={currentStatus}
                                    onChange={(e) =>
                                      setPendingStatus((p) => ({
                                        ...p,
                                        [c.case_id]: e.target.value,
                                      }))
                                    }
                                    className="text-xs rounded-md bg-slate-800 border border-slate-700 px-2 py-1.5 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                                  >
                                    <option value="open">Open</option>
                                    <option value="in_progress">In Progress</option>
                                    <option value="escalated">Escalated</option>
                                    <option value="closed">Closed</option>
                                  </select>

                                  <input
                                    type="text"
                                    placeholder="Add a note (optional)…"
                                    value={pendingNotes[c.case_id] ?? ""}
                                    onChange={(e) =>
                                      setPendingNotes((p) => ({
                                        ...p,
                                        [c.case_id]: e.target.value,
                                      }))
                                    }
                                    className="flex-1 min-w-[200px] text-xs rounded-md bg-slate-800 border border-slate-700 px-2 py-1.5 text-white placeholder-slate-600 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                                  />

                                  <button
                                    onClick={() =>
                                      handleUpdate(c.case_id, c.status)
                                    }
                                    disabled={saving === c.case_id}
                                    className="px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                  >
                                    {saving === c.case_id ? "Saving…" : "Save"}
                                  </button>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}
