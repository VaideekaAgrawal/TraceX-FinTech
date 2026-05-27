"use client";
import { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-700/50 bg-[#111827] p-5 ${className}`}>
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  icon,
  color = "blue",
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon?: string;
  color?: "blue" | "red" | "orange" | "green" | "purple" | "yellow";
}) {
  const colorMap = {
    blue: "from-blue-500/20 to-blue-600/5 border-blue-500/20",
    red: "from-red-500/20 to-red-600/5 border-red-500/20",
    orange: "from-orange-500/20 to-orange-600/5 border-orange-500/20",
    green: "from-green-500/20 to-green-600/5 border-green-500/20",
    purple: "from-purple-500/20 to-purple-600/5 border-purple-500/20",
    yellow: "from-yellow-500/20 to-yellow-600/5 border-yellow-500/20",
  };
  const textColor = {
    blue: "text-blue-400", red: "text-red-400", orange: "text-orange-400",
    green: "text-green-400", purple: "text-purple-400", yellow: "text-yellow-400",
  };

  return (
    <div className={`rounded-xl border bg-gradient-to-br p-5 ${colorMap[color]}`}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</p>
        {icon && <span className="text-lg">{icon}</span>}
      </div>
      <p className={`mt-2 text-2xl font-bold ${textColor[color]}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export function Badge({ children, variant = "default" }: { children: ReactNode; variant?: "default" | "danger" | "warning" | "success" | "info" }) {
  const styles = {
    default: "bg-slate-700 text-slate-300",
    danger: "bg-red-500/20 text-red-400 border border-red-500/30",
    warning: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
    success: "bg-green-500/20 text-green-400 border border-green-500/30",
    info: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[variant]}`}>
      {children}
    </span>
  );
}

export function Loader() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
    </div>
  );
}

export function EmptyState({ message = "No data available" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-slate-500">
      <span className="text-4xl mb-3">📭</span>
      <p className="text-sm">{message}</p>
    </div>
  );
}
