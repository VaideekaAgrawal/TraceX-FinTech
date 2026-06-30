"use client";

import { useState, useEffect, Fragment } from "react";
import Link from "next/link";
import { api, InvestigationCase } from "@/lib/api";
import { Card, StatCard, Badge, Loader, InfoTooltip } from "@/components/ui";

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

function AIExplanationPanel({ accountId }: { accountId: string }) {
  const [explanation, setExplanation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shown, setShown] = useState(false);

  const generate = async () => {
    if (shown && explanation) { setShown(false); return; }
    setShown(true);
    if (explanation) return;
    setLoading(true);
    try {
      const res = await api.getAccountExplanation(accountId);
      setExplanation(res.explanation);
    } catch {
      setExplanation("Could not generate explanation. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-2">
      <button
        onClick={generate}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-violet-600/20 border border-violet-500/30 text-xs text-violet-300 hover:bg-violet-600/30 transition-colors"
      >
        <span>🤖</span>
        <span>{shown && explanation ? "Hide Explanation" : "Why flagged? (AI)"}</span>
      </button>
      {shown && (
        <div className="mt-2 p-3 rounded-lg bg-violet-500/5 border border-violet-500/20">
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-violet-300">
              <span className="h-3 w-3 border border-violet-400/40 border-t-violet-400 rounded-full animate-spin" />
              Generating AI explanation...
            </div>
          ) : (
            <p className="text-xs text-slate-300 leading-relaxed">{explanation}</p>
          )}
        </div>
      )}
    </div>
  );
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
            <h1 className="text-2xl font-bold text-white">Case Management <InfoTooltip text="Case Management tracks investigation cases from initial flag through to STR filing or clearance. Each case preserves the account snapshot, graph state, and investigation notes at the time of escalation." /></h1>
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
            label={<>Open <InfoTooltip text="Cases that have been created but not yet assigned to an investigator. These require triage." /></>}
            value={countByStatus("open")}
            icon="🔵"
            color="blue"
            sub="Awaiting assignment"
          />
          <StatCard
            label={<>In Progress <InfoTooltip text="Cases currently being investigated. An analyst is reviewing transactions, gathering evidence, and determining whether to file an STR." /></>}
            value={countByStatus("in_progress")}
            icon="🟡"
            color="yellow"
            sub="Under investigation"
          />
          <StatCard
            label={<>Escalated <InfoTooltip text="Cases that have been escalated to senior compliance or management. These typically have strong evidence of suspicious activity." /></>}
            value={countByStatus("escalated")}
            icon="🔴"
            color="red"
            sub="Requires action"
          />
          <StatCard
            label={<>Closed <InfoTooltip text="Cases that have been resolved — either by filing an STR with FIU-India or by clearing the account after review." /></>}
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
                                    Account IDs <InfoTooltip text="All accounts involved in this case. Click any account to view its transaction network in the Graph Explorer." />
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

                                {/* AI Brief */}
                                {c.account_ids.slice(0, 1).map((accId: string) => (
                                  <div key={accId} className="mt-3">
                                    <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                                      AI Brief — Primary Account ({accId})
                                    </h4>
                                    <AIExplanationPanel accountId={accId} />
                                  </div>
                                ))}

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
                                  <InfoTooltip text="Updating status records the change with a timestamp. Status history is preserved for audit trail purposes required under PMLA record-keeping obligations." />
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
