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
}

export default function CytoscapeGraph({ data, onNodeClick, className = "" }: CytoscapeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  const buildElements = useCallback((graphData: GraphData): ElementDefinition[] => {
    const elements: ElementDefinition[] = [];

    // Nodes
    for (const node of graphData.nodes) {
      elements.push({
        data: {
          id: node.id,
          label: node.id.replace(/^ACC_/, ""),
          risk_score: node.risk_score,
          risk_level: node.risk_level,
          risk_color: node.risk_color || RISK_COLORS[node.risk_level] || "#6b7280",
          role: node.role,
          is_center: node.is_center || false,
        },
      });
    }

    // Edges
    for (let i = 0; i < graphData.edges.length; i++) {
      const edge = graphData.edges[i];
      elements.push({
        data: {
          id: `e${i}`,
          source: edge.source,
          target: edge.target,
          amount: edge.amount,
          channel: edge.channel,
          label: `₹${(edge.amount / 1000).toFixed(0)}K`,
        },
      });
    }

    return elements;
  }, []);

  useEffect(() => {
    if (!containerRef.current || !data || data.nodes.length === 0) return;

    const elements = buildElements(data);

    // Destroy previous instance
    if (cyRef.current) {
      cyRef.current.destroy();
    }

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
      layout: {
        name: "cose",
        animate: true,
        animationDuration: 800,
        nodeRepulsion: () => 8000,
        idealEdgeLength: () => 80,
        gravity: 0.25,
        numIter: 300,
        randomize: false,
      } as cytoscape.CoseLayoutOptions,
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

    // Fit to viewport after layout
    cy.on("layoutstop", () => {
      cy.fit(undefined, 30);
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [data, buildElements, onNodeClick]);

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
