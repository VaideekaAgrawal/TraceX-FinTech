"use client";

import React, { useEffect, useRef, useCallback } from "react";
import cytoscape, { Core, ElementDefinition } from "cytoscape";
import { GraphData, GraphNode, GraphEdge } from "@/lib/api";

const RISK_COLORS: Record<string, string> = {
  CRITICAL: "#ef4444",
  HIGH: "#f97316",
  MEDIUM: "#eab308",
  LOW: "#22c55e",
};

const ROLE_SHAPES: Record<string, string> = {
  MULE: "diamond",
  SOURCE: "triangle",
  SINK: "vee",
  NORMAL: "ellipse",
};

interface CytoscapeGraphProps {
  data: GraphData | null;
  onNodeClick?: (nodeId: string) => void;
  className?: string;
  layoutHint?: "cose" | "circle" | "breadthfirst" | "concentric";
}

export default function CytoscapeGraph({ data, onNodeClick, className = "", layoutHint }: CytoscapeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  const buildElements = useCallback((graphData: GraphData): ElementDefinition[] => {
    const elements: ElementDefinition[] = [];
    if (!graphData || !graphData.nodes) return elements;

    const nodeIds = new Set<string>();

    // Nodes
    for (const node of graphData.nodes) {
      if (!node || !node.id) continue;
      nodeIds.add(node.id);
      elements.push({
        data: {
          id: node.id,
          label: node.id.replace(/^ACC_/, ""),
          risk_score: node.risk_score ?? 0,
          risk_level: node.risk_level || "LOW",
          risk_color: node.risk_color || RISK_COLORS[node.risk_level] || "#6b7280",
          role: node.role || "NORMAL",
          is_center: node.is_center || false,
        },
      });
    }

    // Edges — only include edges whose source and target exist in the node set
    // Cap at 100 edges client-side — keeps layout fast and browser stable
    const edges = graphData.edges || [];
    const validEdges = edges.filter(e => e && nodeIds.has(e.source) && nodeIds.has(e.target));
    const cappedEdges = validEdges.length > 100
      ? validEdges.sort((a, b) => (b.amount || 0) - (a.amount || 0)).slice(0, 100)
      : validEdges;

    for (let i = 0; i < cappedEdges.length; i++) {
      const edge = cappedEdges[i];
      elements.push({
        data: {
          id: `e${i}`,
          source: edge.source,
          target: edge.target,
          amount: edge.amount || 0,
          channel: edge.channel || "",
          label: `₹${((edge.amount || 0) / 1000).toFixed(0)}K`,
        },
      });
    }

    return elements;
  }, []);

  useEffect(() => {
    if (!containerRef.current || !data || !data.nodes || data.nodes.length === 0) return;

    let elements: ElementDefinition[];
    try {
      elements = buildElements(data);
    } catch (e) {
      console.error("CytoscapeGraph: failed to build elements", e);
      return;
    }

    if (elements.length === 0) return;

    // Destroy previous instance
    if (cyRef.current) {
      try { cyRef.current.destroy(); } catch { /* ignore */ }
      cyRef.current = null;
    }

    try {
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(risk_color)",
            label: "data(label)",
            "font-size": "10px",
            color: "#e2e8f0",
            "text-outline-color": "#0b1120",
            "text-outline-width": 2,
            "text-valign": "bottom",
            "text-margin-y": 5,
            width: "mapData(risk_score, 0, 100, 20, 50)",
            height: "mapData(risk_score, 0, 100, 20, 50)",
            shape: (ele: cytoscape.NodeSingular) => {
              const role = ele.data("role") || "NORMAL";
              return ROLE_SHAPES[role] || "ellipse";
            },
            "border-width": 2,
            "border-color": "#1e293b",
            "overlay-opacity": 0,
          } as cytoscape.Css.Node,
        },
        {
          selector: "node[?is_center]",
          style: {
            "border-width": 4,
            "border-color": "#ffffff",
            "font-weight": "bold",
            "font-size": "12px",
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 4,
            "border-color": "#60a5fa",
            "background-opacity": 1,
          },
        },
        {
          selector: "edge",
          style: {
            width: "mapData(amount, 0, 1000000, 1, 5)",
            "line-color": "#475569",
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.6,
            "font-size": "8px",
            color: "#94a3b8",
            "text-outline-color": "#0b1120",
            "text-outline-width": 1,
          } as cytoscape.Css.Edge,
        },
        {
          selector: "edge:selected",
          style: {
            "line-color": "#60a5fa",
            "target-arrow-color": "#60a5fa",
            opacity: 1,
            label: "data(label)",
          },
        },
      ],
      layout: (() => {
        switch (layoutHint) {
          case "circle":
            return { name: "circle", animate: false, spacingFactor: 1.5 };
          case "breadthfirst":
            return { name: "breadthfirst", animate: false, directed: true, spacingFactor: 1.2 };
          case "concentric":
            return {
              name: "concentric",
              animate: false,
              concentric: (node: cytoscape.NodeSingular) => node.data("risk_score") || 0,
              levelWidth: () => 2,
            };
          default:
            return {
              name: "cose",
              animate: false,
              nodeRepulsion: () => 4000,
              idealEdgeLength: () => 120,
              gravity: 0.4,
              numIter: 30,
              randomize: false,
            };
        }
      })() as cytoscape.CoseLayoutOptions,
      wheelSensitivity: 0.3,
      minZoom: 0.2,
      maxZoom: 4,
    });

    // Event handlers
    cy.on("tap", "node", (evt) => {
      const nodeId = evt.target.id();
      if (onNodeClick) onNodeClick(nodeId);
    });

    // Hover effects
    cy.on("mouseover", "node", (evt) => {
      const node = evt.target;
      node.style("border-color", "#ffffff");
      node.style("border-width", 3);
      containerRef.current!.style.cursor = "pointer";
    });

    cy.on("mouseout", "node", (evt) => {
      const node = evt.target;
      if (!node.selected()) {
        node.style("border-color", "#1e293b");
        node.style("border-width", 2);
      }
      containerRef.current!.style.cursor = "default";
    });

    // Show edge labels on hover
    cy.on("mouseover", "edge", (evt) => {
      evt.target.style("label", evt.target.data("label"));
      evt.target.style("opacity", 1);
    });

    cy.on("mouseout", "edge", (evt) => {
      if (!evt.target.selected()) {
        evt.target.style("label", "");
        evt.target.style("opacity", 0.6);
      }
    });

    cyRef.current = cy;

    // Fit to viewport after layout — guard against destroyed instance
    cy.one("layoutstop", () => {
      if (cyRef.current && containerRef.current) {
        try { cy.fit(undefined, 30); } catch { /* ignore */ }
      }
    });

    } catch (e) {
      console.error("CytoscapeGraph: failed to initialize cytoscape", e);
    }

    return () => {
      if (cyRef.current) {
        try { cyRef.current.destroy(); } catch { /* ignore */ }
        cyRef.current = null;
      }
    };
  }, [data, buildElements, onNodeClick, layoutHint]);

  if (!data || data.nodes.length === 0) {
    return (
      <div className={`flex items-center justify-center h-full text-slate-500 ${className}`}>
        <p className="text-sm">No graph data to display</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`w-full h-full bg-[#0b1120] rounded-lg ${className}`} />
  );
}
