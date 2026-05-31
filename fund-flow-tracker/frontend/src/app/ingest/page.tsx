"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Card, Loader } from "@/components/ui";

interface IngestionResult {
  status: string;
  date?: string;
  total_transactions?: number;
  total_accounts?: number;
  new_accounts?: number;
  existing_accounts?: number;
  alerts_generated?: number;
  patterns_detected?: Record<string, number>;
  processing_time_sec?: number;
  system_refreshed?: boolean;
  refresh_warning?: string;
  reason?: string;
  file_hash?: string;
}

export default function IngestPage() {
  const [file, setFile] = useState<File | null>(null);
  const [date, setDate] = useState("");
  const [force, setForce] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IngestionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [history, setHistory] = useState<Record<string, unknown>[] | null>(null);
  const [loadingHistory, setLoadingHistory] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.getIngestionHistory();
      setHistory(h);
    } catch {
      // ignore
    }
  }, []);

  // Auto-load history on mount
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const handleLoadFromHistory = async (filename: string) => {
    setLoadingHistory(filename);
    setError(null);
    try {
      const resp = await api.refreshSystem();
      setResult({
        status: "completed",
        system_refreshed: true,
        total_accounts: resp.accounts as number,
        total_transactions: resp.transactions as number,
      });
      // Navigate to dashboard after a short delay
      setTimeout(() => { window.location.href = "/"; }, 1500);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load system from database");
    } finally {
      setLoadingHistory(null);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith(".csv")) {
      setFile(f);
      setError(null);
    } else {
      setError("Please upload a CSV file");
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setError(null);
    }
  };

  const handleSubmit = async () => {
    if (!file) {
      setError("Please select a CSV file to upload");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.ingestUpload(file, date || undefined, force) as unknown as IngestionResult;
      setResult(res);
      loadHistory();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0b1120] p-6 text-white max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <span className="text-3xl">📥</span> TraceX — EOD Transaction Ingestion
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Upload daily transaction CSV to process and detect fraud patterns
          </p>
        </div>
        <button
          onClick={loadHistory}
          className="px-3 py-1.5 rounded-lg bg-slate-800 text-xs text-slate-300 hover:bg-slate-700 border border-slate-700"
        >
          View History
        </button>
      </div>

      {/* Upload Section */}
      <Card>
        <div className="p-6 space-y-5">
          <h2 className="text-lg font-semibold text-white">Upload Transaction CSV</h2>
          <p className="text-xs text-slate-400">
            Upload a CSV file with transaction data (required columns: timestamp, source_account, dest_account, amount; optional: channel, txn_type, txn_id).
            The system will automatically detect fraud patterns, classify risk, and flag suspicious transactions.
          </p>

          {/* Drag & Drop Area */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
              dragActive
                ? "border-blue-500 bg-blue-500/10"
                : file
                ? "border-emerald-500/50 bg-emerald-500/5"
                : "border-slate-700 hover:border-slate-500 bg-slate-900/50"
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              className="hidden"
            />
            {file ? (
              <div className="space-y-2">
                <div className="text-4xl">✅</div>
                <p className="text-sm font-medium text-emerald-400">{file.name}</p>
                <p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                <p className="text-xs text-slate-500">Click or drop to replace</p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-4xl">📄</div>
                <p className="text-sm text-slate-300">Drag & drop your CSV file here</p>
                <p className="text-xs text-slate-500">or click to browse</p>
              </div>
            )}
          </div>

          {/* Options */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Ingestion Date (optional)</label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={force}
                  onChange={(e) => setForce(e.target.checked)}
                  className="rounded bg-slate-800 border-slate-700 text-blue-500 focus:ring-blue-500"
                />
                <span className="text-xs text-slate-400">Force re-process (skip duplicate check)</span>
              </label>
            </div>
            <div className="flex items-end justify-end">
              <button
                onClick={handleSubmit}
                disabled={!file || loading}
                className={`px-6 py-2.5 rounded-lg font-medium text-sm transition-all ${
                  !file || loading
                    ? "bg-slate-700 text-slate-500 cursor-not-allowed"
                    : "bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-600/20"
                }`}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Processing...
                  </span>
                ) : (
                  "🚀 Process & Analyze"
                )}
              </button>
            </div>
          </div>
        </div>
      </Card>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
          <p className="text-sm text-red-400">❌ {error}</p>
        </div>
      )}

      {/* Loading Progress */}
      {loading && (
        <Card>
          <div className="p-6 text-center space-y-3">
            <div className="h-8 w-8 border-3 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto" />
            <p className="text-sm text-slate-300">Processing transactions...</p>
            <p className="text-xs text-slate-500">Running fraud detection, pattern analysis, and risk scoring</p>
          </div>
        </Card>
      )}

      {/* Results */}
      {result && (
        <Card>
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                {result.status === "completed" ? "✅" : result.status === "skipped" ? "⏭️" : "❌"}
                Ingestion {result.status === "completed" ? "Complete" : result.status === "skipped" ? "Skipped (Duplicate)" : "Failed"}
              </h2>
              {result.processing_time_sec && (
                <span className="text-xs text-slate-500">{result.processing_time_sec}s</span>
              )}
            </div>

            {result.status === "skipped" && (
              <p className="text-sm text-yellow-400">This file was already processed. Enable &quot;Force re-process&quot; to ingest again.</p>
            )}

            {result.status === "completed" && (
              <>
                {/* Stats Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50">
                    <p className="text-xs text-slate-500">Transactions</p>
                    <p className="text-xl font-bold text-white">{result.total_transactions?.toLocaleString()}</p>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50">
                    <p className="text-xs text-slate-500">Total Accounts</p>
                    <p className="text-xl font-bold text-white">{result.total_accounts?.toLocaleString()}</p>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50">
                    <p className="text-xs text-slate-500">New Accounts</p>
                    <p className="text-xl font-bold text-emerald-400">{result.new_accounts?.toLocaleString()}</p>
                  </div>
                  <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50">
                    <p className="text-xs text-slate-500">Alerts Generated</p>
                    <p className="text-xl font-bold text-red-400">{result.alerts_generated?.toLocaleString()}</p>
                  </div>
                </div>

                {/* Patterns Detected */}
                {result.patterns_detected && Object.keys(result.patterns_detected).length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-slate-300 mb-2">Patterns Detected</h3>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(result.patterns_detected).map(([pattern, count]) => (
                        <span
                          key={pattern}
                          className="px-2.5 py-1 rounded-full bg-orange-500/10 border border-orange-500/30 text-xs text-orange-400"
                        >
                          {pattern}: {count}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* System Refresh Status */}
                {result.system_refreshed !== undefined && (
                  <div className={`rounded-lg p-3 text-xs ${result.system_refreshed ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400" : "bg-yellow-500/10 border border-yellow-500/20 text-yellow-400"}`}>
                    {result.system_refreshed
                      ? "✅ System state refreshed — all views (graph, anomaly, patterns) are updated with new data."
                      : `⚠️ Data ingested to DB but in-memory views may need manual refresh. ${result.refresh_warning || ""}`}
                  </div>
                )}

                {/* Navigation to other pages — open in new tabs so user can view all analyses */}
                <div className="flex flex-wrap gap-2 pt-2">
                  <a href="/" target="_blank" rel="noopener noreferrer" className="px-3 py-1.5 rounded-lg bg-blue-600/20 border border-blue-500/30 text-xs text-blue-400 hover:bg-blue-600/30">
                    📊 View Dashboard ↗
                  </a>
                  <a href="/graph" target="_blank" rel="noopener noreferrer" className="px-3 py-1.5 rounded-lg bg-purple-600/20 border border-purple-500/30 text-xs text-purple-400 hover:bg-purple-600/30">
                    🔍 Explore Graph ↗
                  </a>
                  <a href="/anomaly" target="_blank" rel="noopener noreferrer" className="px-3 py-1.5 rounded-lg bg-red-600/20 border border-red-500/30 text-xs text-red-400 hover:bg-red-600/30">
                    ⚠️ View Anomalies ↗
                  </a>
                  <a href="/patterns" target="_blank" rel="noopener noreferrer" className="px-3 py-1.5 rounded-lg bg-orange-600/20 border border-orange-500/30 text-xs text-orange-400 hover:bg-orange-600/30">
                    🔄 View Patterns ↗
                  </a>
                </div>
              </>
            )}
          </div>
        </Card>
      )}

      {/* Ingestion History */}
      {history && (
        <Card>
          <div className="p-6 space-y-3">
            <h2 className="text-lg font-semibold text-white">📜 Ingestion History</h2>
            {history.length === 0 ? (
              <p className="text-sm text-slate-500">No previous ingestions found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-700">
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">File</th>
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Date</th>
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Transactions</th>
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Accounts</th>
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Status</th>
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Processed At</th>
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item, idx) => {
                      const filename = String(item.filename || "");
                      const isLoading = loadingHistory === filename;
                      return (
                        <tr key={idx} className="border-b border-slate-800 hover:bg-slate-800/50">
                          <td className="py-2 px-2 text-slate-300">{filename || "-"}</td>
                          <td className="py-2 px-2 text-slate-400">{String(item.ingestion_date || "-")}</td>
                          <td className="py-2 px-2 text-slate-300">{Number(item.num_transactions || 0).toLocaleString()}</td>
                          <td className="py-2 px-2 text-slate-300">{Number(item.num_accounts || 0).toLocaleString()}</td>
                          <td className="py-2 px-2">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${item.status === "completed" ? "bg-emerald-500/20 text-emerald-400" : "bg-yellow-500/20 text-yellow-400"}`}>
                              {String(item.status || "unknown")}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-slate-500">{String(item.created_at || "-")}</td>
                          <td className="py-2 px-2">
                            <button
                              onClick={() => handleLoadFromHistory(filename)}
                              disabled={isLoading}
                              className={`px-2 py-1 rounded text-[10px] font-medium transition-all ${
                                isLoading
                                  ? "bg-blue-600/30 text-blue-300 cursor-wait"
                                  : "bg-blue-600/20 border border-blue-500/30 text-blue-400 hover:bg-blue-600/40"
                              }`}
                            >
                              {isLoading ? "Loading..." : "🔄 Load & Analyze"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Instructions */}
      <Card>
        <div className="p-6 space-y-3">
          <h2 className="text-sm font-semibold text-slate-300">ℹ️ How It Works</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-400">
            <div className="space-y-1">
              <p className="font-medium text-white">1. Upload CSV</p>
              <p>Upload your end-of-day transaction dump in the standard format (same columns as training data).</p>
            </div>
            <div className="space-y-1">
              <p className="font-medium text-white">2. Incremental Analysis</p>
              <p>New accounts are analyzed on today&apos;s data. Existing accounts use 7-day rolling window for pattern detection.</p>
            </div>
            <div className="space-y-1">
              <p className="font-medium text-white">3. Updated Results</p>
              <p>Graph, anomaly scores, risk levels, and patterns are all updated. Navigate to any page to see latest results.</p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
