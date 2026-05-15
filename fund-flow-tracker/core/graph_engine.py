"""
Graph Engine for TraceX — NetworkX MultiDiGraph with temporal BFS,
cycle detection, centrality, fund trails, and suspicious path ranking.
"""
import networkx as nx
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict


class TransactionGraph:
    """Core graph engine built on NetworkX MultiDiGraph."""

    def __init__(self, accounts_df: pd.DataFrame, transactions_df: pd.DataFrame):
        self.accounts_df = accounts_df
        self.transactions_df = transactions_df
        self.G = nx.MultiDiGraph()
        self._build_graph()
        self._centrality_cache: Dict[str, Dict] = {}

    def _build_graph(self):
        """Build graph from transaction data. Nodes = accounts, Edges = transactions."""
        # Add account nodes with metadata
        for _, row in self.accounts_df.iterrows():
            self.G.add_node(row["account_id"], **row.to_dict())

        # Add transaction edges
        for _, row in self.transactions_df.iterrows():
            src = row["source_account"]
            dst = row["dest_account"]
            # Ensure nodes exist even if not in accounts_df
            if src not in self.G:
                self.G.add_node(src, account_id=src)
            if dst not in self.G:
                self.G.add_node(dst, account_id=dst)

            self.G.add_edge(
                src, dst,
                txn_id=row.get("txn_id", ""),
                timestamp=row["timestamp"],
                amount=row["amount"],
                channel=row.get("channel", "unknown"),
                txn_type=row.get("txn_type", "transfer"),
                is_laundering=row.get("is_laundering", 0),
            )

    # ------------------------------------------------------------------
    # Centrality computations (cached)
    # ------------------------------------------------------------------
    def _get_simple_digraph(self) -> nx.DiGraph:
        """Collapse multi-edges into weighted single edges for centrality."""
        simple = nx.DiGraph()
        for u, v, data in self.G.edges(data=True):
            if simple.has_edge(u, v):
                simple[u][v]["weight"] += data.get("amount", 1.0)
                simple[u][v]["count"] += 1
            else:
                simple.add_edge(u, v, weight=data.get("amount", 1.0), count=1)
        return simple

    def compute_centrality(self) -> Dict[str, Dict]:
        """Compute PageRank and betweenness centrality (cached)."""
        if self._centrality_cache:
            return self._centrality_cache

        simple_g = self._get_simple_digraph()

        if len(simple_g) == 0:
            self._centrality_cache = {"pagerank": {}, "betweenness": {}}
            return self._centrality_cache

        pr = nx.pagerank(simple_g, weight="weight", alpha=0.85, max_iter=100)
        # Betweenness on large graphs: sample for performance
        k = min(len(simple_g), 500)
        bc = nx.betweenness_centrality(simple_g, weight="weight", normalized=True, k=k)

        self._centrality_cache = {"pagerank": pr, "betweenness": bc}
        return self._centrality_cache

    def get_pagerank(self) -> Dict[str, float]:
        return self.compute_centrality()["pagerank"]

    def get_betweenness(self) -> Dict[str, float]:
        return self.compute_centrality()["betweenness"]

    # ------------------------------------------------------------------
    # Temporal BFS — money can only flow forward in time
    # ------------------------------------------------------------------
    def temporal_bfs(self, start_account: str, direction: str = "forward",
                     max_depth: int = 5, start_time: Optional[pd.Timestamp] = None) -> List[Dict]:
        """
        BFS that respects temporal ordering.
        direction: 'forward' (follow money), 'backward' (trace source), 'both'.
        """
        if start_account not in self.G:
            return []

        if start_time is None:
            # Use earliest transaction involving this account
            edges = list(self.G.in_edges(start_account, data=True)) + \
                    list(self.G.out_edges(start_account, data=True))
            if not edges:
                return []
            timestamps = [d.get("timestamp", pd.Timestamp.min) for *_, d in edges]
            start_time = min(timestamps)

        visited = set()
        queue = [(start_account, start_time, 0, [])]
        trails = []

        while queue:
            node, current_time, depth, path = queue.pop(0)
            if depth >= max_depth:
                continue

            if direction in ("forward", "both"):
                for _, neighbor, key, data in self.G.out_edges(node, data=True, keys=True):
                    edge_time = data.get("timestamp", pd.Timestamp.min)
                    edge_key = (node, neighbor, key)
                    if edge_time >= current_time and edge_key not in visited:
                        visited.add(edge_key)
                        new_path = path + [{
                            "from": node, "to": neighbor,
                            "amount": data.get("amount", 0),
                            "timestamp": edge_time,
                            "channel": data.get("channel", ""),
                            "txn_id": data.get("txn_id", ""),
                        }]
                        trails.append(new_path)
                        queue.append((neighbor, edge_time, depth + 1, new_path))

            if direction in ("backward", "both"):
                for neighbor, _, key, data in self.G.in_edges(node, data=True, keys=True):
                    edge_time = data.get("timestamp", pd.Timestamp.max)
                    edge_key = (neighbor, node, key)
                    if edge_time <= current_time and edge_key not in visited:
                        visited.add(edge_key)
                        new_path = path + [{
                            "from": neighbor, "to": node,
                            "amount": data.get("amount", 0),
                            "timestamp": edge_time,
                            "channel": data.get("channel", ""),
                            "txn_id": data.get("txn_id", ""),
                        }]
                        trails.append(new_path)
                        queue.append((neighbor, edge_time, depth + 1, new_path))

        return trails

    def get_fund_trail(self, account_id: str, direction: str = "both",
                       max_depth: int = 5) -> Dict[str, Any]:
        """Get fund trail for an account with component info."""
        if account_id not in self.G:
            return {"error": "Account not found", "account_id": account_id, "trails": []}

        # Check component
        undirected = self.G.to_undirected()
        if account_id in undirected:
            component = nx.node_connected_component(undirected, account_id)
            component_size = len(component)
        else:
            component_size = 1

        if component_size == 1:
            return {
                "account_id": account_id,
                "warning": "Isolated account — no connections found",
                "component_size": 1,
                "trails": [],
            }

        trails = self.temporal_bfs(account_id, direction, max_depth)
        return {
            "account_id": account_id,
            "component_size": component_size,
            "trail_count": len(trails),
            "trails": trails,
        }

    # ------------------------------------------------------------------
    # Cycle detection (bounded, safe)
    # ------------------------------------------------------------------
    def detect_cycles(self, max_length: int = 5, max_cycles: int = 200) -> List[List[str]]:
        """Safe cycle detection with length bound."""
        simple_g = self._get_simple_digraph()
        try:
            cycles = []
            for cycle in nx.simple_cycles(simple_g, length_bound=max_length):
                cycles.append(cycle)
                if len(cycles) >= max_cycles:
                    break
            return cycles
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Connected components
    # ------------------------------------------------------------------
    def get_components(self) -> List[set]:
        """Get weakly connected components sorted by size."""
        components = list(nx.weakly_connected_components(self.G))
        return sorted(components, key=len, reverse=True)

    # ------------------------------------------------------------------
    # Ego subgraph for visualization
    # ------------------------------------------------------------------
    def get_ego_subgraph(self, account_id: str, radius: int = 2) -> nx.MultiDiGraph:
        """Get N-hop neighborhood subgraph of a given account."""
        if account_id not in self.G:
            return nx.MultiDiGraph()
        nodes = {account_id}
        frontier = {account_id}
        for _ in range(radius):
            new_frontier = set()
            for node in frontier:
                new_frontier.update(self.G.successors(node))
                new_frontier.update(self.G.predecessors(node))
            frontier = new_frontier - nodes
            nodes.update(frontier)
        return self.G.subgraph(nodes).copy()

    # ------------------------------------------------------------------
    # Top-N risky subgraph for rendering
    # ------------------------------------------------------------------
    def get_renderable_subgraph(self, risk_scores: Dict[str, float],
                                max_nodes: int = 100) -> nx.MultiDiGraph:
        """Get subgraph of top-risk nodes + their 1-hop neighbors."""
        sorted_accs = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)
        seed_nodes = set()
        for acc, _ in sorted_accs:
            if acc in self.G:
                seed_nodes.add(acc)
            if len(seed_nodes) >= max_nodes // 2:
                break

        all_nodes = set(seed_nodes)
        for node in seed_nodes:
            all_nodes.update(list(self.G.successors(node))[:5])
            all_nodes.update(list(self.G.predecessors(node))[:5])

        nodes = list(all_nodes)[:max_nodes]
        return self.G.subgraph(nodes).copy()

    # ------------------------------------------------------------------
    # Transaction chains for speed analysis
    # ------------------------------------------------------------------
    def get_transaction_chains(self, min_hops: int = 3,
                               time_window_minutes: int = 30) -> List[List[Dict]]:
        """Extract temporal transaction chains from the graph."""
        chains = []
        # Sort edges by timestamp
        edges = []
        for u, v, data in self.G.edges(data=True):
            ts = data.get("timestamp")
            if ts is not None:
                edges.append((u, v, data))

        edges.sort(key=lambda x: x[2].get("timestamp", pd.Timestamp.min))

        visited_starts = set()
        for u, v, data in edges:
            if u in visited_starts:
                continue
            chain = [{
                "from": u, "to": v,
                "amount": data.get("amount", 0),
                "timestamp": data.get("timestamp"),
                "channel": data.get("channel", ""),
            }]
            current_node = v
            current_time = data.get("timestamp")
            window_end = current_time + pd.Timedelta(minutes=time_window_minutes) if current_time else None

            # Follow the chain
            for _ in range(20):  # Max chain length guard
                out_edges = list(self.G.out_edges(current_node, data=True))
                next_edge = None
                for _, next_v, next_data in out_edges:
                    next_time = next_data.get("timestamp")
                    if next_time and current_time and window_end:
                        if current_time <= next_time <= window_end:
                            next_edge = (current_node, next_v, next_data)
                            break

                if next_edge is None:
                    break

                _, nv, nd = next_edge
                chain.append({
                    "from": current_node, "to": nv,
                    "amount": nd.get("amount", 0),
                    "timestamp": nd.get("timestamp"),
                    "channel": nd.get("channel", ""),
                })
                current_node = nv
                current_time = nd.get("timestamp")

            if len(chain) >= min_hops:
                chains.append(chain)
                visited_starts.add(u)

        return chains

    # ------------------------------------------------------------------
    # Path ranking
    # ------------------------------------------------------------------
    def rank_suspicious_paths(self, risk_scores: Dict[str, float],
                              top_n: int = 10) -> List[Dict]:
        """Rank fund-flow paths by aggregate risk."""
        chains = self.get_transaction_chains(min_hops=2, time_window_minutes=60)
        scored_paths = []
        for chain in chains:
            accounts_in_chain = set()
            total_amount = 0
            for step in chain:
                accounts_in_chain.add(step["from"])
                accounts_in_chain.add(step["to"])
                total_amount += step.get("amount", 0)

            avg_risk = np.mean([risk_scores.get(a, 0) for a in accounts_in_chain])
            max_risk = max([risk_scores.get(a, 0) for a in accounts_in_chain])

            scored_paths.append({
                "chain": chain,
                "hops": len(chain),
                "total_amount": total_amount,
                "accounts": list(accounts_in_chain),
                "avg_risk": avg_risk,
                "max_risk": max_risk,
                "path_score": avg_risk * 0.4 + max_risk * 0.4 + min(len(chain) / 10, 1) * 20,
            })

        scored_paths.sort(key=lambda x: x["path_score"], reverse=True)
        return scored_paths[:top_n]

    # ------------------------------------------------------------------
    # Random walk with restart (accomplice detection)
    # ------------------------------------------------------------------
    def random_walk_with_restart(self, start_node: str,
                                 restart_prob: float = 0.15,
                                 num_steps: int = 5000) -> Dict[str, float]:
        """Random walk with restart from a suspicious account to find likely accomplices."""
        if start_node not in self.G or self.G.degree(start_node) == 0:
            return {}

        rng = np.random.default_rng(42)
        visit_counts: Dict[str, int] = defaultdict(int)
        current = start_node

        for _ in range(num_steps):
            visit_counts[current] += 1
            if rng.random() < restart_prob:
                current = start_node
                continue

            neighbors = list(self.G.successors(current)) + list(self.G.predecessors(current))
            if not neighbors:
                current = start_node
                continue
            current = rng.choice(neighbors)

        total = sum(visit_counts.values())
        probs = {k: v / total for k, v in visit_counts.items() if k != start_node}
        return dict(sorted(probs.items(), key=lambda x: x[1], reverse=True))

    # ------------------------------------------------------------------
    # Graph statistics
    # ------------------------------------------------------------------
    def get_stats(self) -> Dict[str, Any]:
        """Return graph-level statistics."""
        return {
            "num_nodes": self.G.number_of_nodes(),
            "num_edges": self.G.number_of_edges(),
            "num_components": nx.number_weakly_connected_components(self.G),
            "density": nx.density(self.G),
            "avg_in_degree": np.mean([d for _, d in self.G.in_degree()]) if len(self.G) > 0 else 0,
            "avg_out_degree": np.mean([d for _, d in self.G.out_degree()]) if len(self.G) > 0 else 0,
        }
