"""
Graph Engine — NetworkX MultiDiGraph with temporal traversal, cycle detection,
centrality computation, and fund trail extraction.

In production, swap NetworkX for Neo4j via CDC (Change Data Capture).
The service interface stays identical.
"""
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

import networkx as nx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TransactionGraph:
    """Core graph engine built on NetworkX MultiDiGraph."""

    def __init__(self, accounts_df: pd.DataFrame, transactions_df: pd.DataFrame):
        self.accounts_df = accounts_df
        self.transactions_df = transactions_df
        self.G = nx.MultiDiGraph()
        self._centrality_cache: Dict[str, Dict] = {}
        self._build()

    # ── Construction ──────────────────────────────────────────────────

    def _build(self):
        """Build graph: nodes = accounts, edges = transactions (memory-safe)."""
        # ── Nodes — only IDs, no attribute dict (saves ~500 MB for large datasets) ──
        all_src = self.transactions_df["source_account"].values
        all_dst = self.transactions_df["dest_account"].values
        all_accts = np.union1d(all_src, all_dst)
        self.G.add_nodes_from(all_accts.tolist())

        # ── Edges — store ONLY amount + is_laundering (minimal per-edge memory) ──
        # Storing timestamp/channel/txn_type in 5M edge dicts wastes ~2 GB.
        # Pattern detectors that need those fields use transactions_df directly.
        has_label = "is_laundering" in self.transactions_df.columns
        src_col = self.transactions_df["source_account"].values
        dst_col = self.transactions_df["dest_account"].values
        amt_col = self.transactions_df["amount"].values
        lbl_col = self.transactions_df["is_laundering"].values if has_label else np.zeros(len(src_col), dtype=np.int8)

        BATCH = 200_000
        batch = []
        for i in range(len(src_col)):
            batch.append((src_col[i], dst_col[i],
                          {"amount": float(amt_col[i]), "is_laundering": int(lbl_col[i])}))
            if len(batch) == BATCH:
                self.G.add_edges_from(batch)
                batch.clear()
        if batch:
            self.G.add_edges_from(batch)

        logger.info("Graph built: %d nodes, %d edges",
                    self.G.number_of_nodes(), self.G.number_of_edges())

    # ── Centrality (cached) ──────────────────────────────────────────

    def _simple_digraph(self) -> nx.DiGraph:
        """Build a lightweight weighted DiGraph from transactions_df (avoids iterating 5M edges)."""
        agg = (
            self.transactions_df
            .groupby(["source_account", "dest_account"], sort=False)["amount"]
            .sum()
            .reset_index()
        )
        agg.columns = ["source", "dest", "weight"]
        simple = nx.from_pandas_edgelist(
            agg, source="source", target="dest",
            edge_attr="weight", create_using=nx.DiGraph()
        )
        del agg
        return simple

    def compute_centrality(self) -> Dict[str, Dict]:
        """
        Fast pandas-based centrality approximations — avoids rebuilding a 5M-edge
        NetworkX DiGraph and running slow BFS-based betweenness on 515k nodes.

        PageRank approx  : normalised weighted in-flow per node (proportional to
                           true PageRank in transaction graphs where amount ≈ weight).
        Betweenness approx: normalised product of in-degree × out-degree.
                           Nodes that bridge many counterparties score high.
        """
        if self._centrality_cache:
            return self._centrality_cache

        txns = self.transactions_df

        # ── PageRank ≈ normalised weighted in-flow ─────────────────────────
        in_flow = txns.groupby("dest_account")["amount"].sum()
        total   = float(in_flow.sum()) or 1.0
        pr      = (in_flow / total).to_dict()

        # ── Betweenness ≈ normalised in-degree × out-degree ────────────────
        in_deg  = txns.groupby("dest_account")["source_account"].nunique().rename("in_d")
        out_deg = txns.groupby("source_account")["dest_account"].nunique().rename("out_d")
        both    = pd.concat([in_deg, out_deg], axis=1).fillna(0)
        raw_bc  = both["in_d"] * both["out_d"]
        max_bc  = float(raw_bc.max()) or 1.0
        bc      = (raw_bc / max_bc).to_dict()

        self._centrality_cache = {"pagerank": pr, "betweenness": bc}
        logger.info("Centrality computed (fast pandas approx): %d nodes", len(pr))
        return self._centrality_cache

    def get_pagerank(self) -> Dict[str, float]:
        return self.compute_centrality()["pagerank"]

    def get_betweenness(self) -> Dict[str, float]:
        return self.compute_centrality()["betweenness"]

    # ── Temporal BFS ─────────────────────────────────────────────────

    def temporal_bfs(self, start: str, direction: str = "forward",
                     max_depth: int = 5,
                     start_time: Optional[pd.Timestamp] = None) -> List[List[Dict]]:
        """
        BFS respecting temporal ordering — money only flows forward in time.
        Returns list of trails, each trail is a list of hop dicts.
        """
        if start not in self.G:
            return []

        if start_time is None:
            edges = list(self.G.in_edges(start, data=True)) + list(self.G.out_edges(start, data=True))
            if not edges:
                return []
            timestamps = [d.get("timestamp", pd.Timestamp.min) for *_, d in edges]
            start_time = min(timestamps)

        visited: Set = set()
        queue = [(start, start_time, 0, [])]
        trails = []

        while queue:
            node, current_time, depth, path = queue.pop(0)
            if depth >= max_depth:
                continue

            if direction in ("forward", "both"):
                for _, nbr, key, data in self.G.out_edges(node, data=True, keys=True):
                    et = data.get("timestamp", pd.Timestamp.min)
                    ek = (node, nbr, key)
                    if et >= current_time and ek not in visited:
                        visited.add(ek)
                        hop = {
                            "from": node, "to": nbr,
                            "amount": data.get("amount", 0),
                            "timestamp": et,
                            "channel": data.get("channel", ""),
                            "txn_id": data.get("txn_id", ""),
                        }
                        new_path = path + [hop]
                        trails.append(new_path)
                        queue.append((nbr, et, depth + 1, new_path))

            if direction in ("backward", "both"):
                for nbr, _, key, data in self.G.in_edges(node, data=True, keys=True):
                    et = data.get("timestamp", pd.Timestamp.max)
                    ek = (nbr, node, key)
                    if et <= current_time and ek not in visited:
                        visited.add(ek)
                        hop = {
                            "from": nbr, "to": node,
                            "amount": data.get("amount", 0),
                            "timestamp": et,
                            "channel": data.get("channel", ""),
                            "txn_id": data.get("txn_id", ""),
                        }
                        new_path = path + [hop]
                        trails.append(new_path)
                        queue.append((nbr, et, depth + 1, new_path))

        return trails

    def get_fund_trail(self, account_id: str, direction: str = "both",
                       max_depth: int = 5) -> Dict[str, Any]:
        if account_id not in self.G:
            return {"error": "Account not found", "account_id": account_id, "trails": []}

        undirected = self.G.to_undirected()
        component = nx.node_connected_component(undirected, account_id)
        if len(component) == 1:
            return {
                "account_id": account_id,
                "warning": "Isolated account — no connections",
                "component_size": 1,
                "trails": [],
            }

        trails = self.temporal_bfs(account_id, direction, max_depth)
        return {
            "account_id": account_id,
            "component_size": len(component),
            "trail_count": len(trails),
            "trails": trails,
        }

    # ── Cycle detection (bounded) ────────────────────────────────────

    def detect_cycles(self, max_length: int = 5, max_cycles: int = 500) -> List[List[str]]:
        """Safe cycle detection with Johnson's algorithm + length bound.
        Prioritises SHORT cycles (2-3 nodes) first since those are the strongest
        round-trip signals, then fills remaining budget with longer cycles."""
        sg = self._simple_digraph()
        MAX_SCC_SIZE = 500
        candidate_nodes = set()
        for scc in nx.strongly_connected_components(sg):
            if 2 <= len(scc) <= MAX_SCC_SIZE:
                candidate_nodes.update(scc)
            if len(candidate_nodes) > 50000:
                break
        if not candidate_nodes:
            return []
        sg = sg.subgraph(candidate_nodes).copy()
        logger.info("Cycle detection: %d candidate nodes in SCCs (max_length=%d)", sg.number_of_nodes(), max_length)
        cycles = []
        seen_sets: Set[frozenset] = set()
        try:
            # Pass 1: Find short cycles first (length 2-3) — strongest RT signal
            for cycle in nx.simple_cycles(sg, length_bound=3):
                cs = frozenset(cycle)
                if cs not in seen_sets:
                    cycles.append(cycle)
                    seen_sets.add(cs)
                if len(cycles) >= max_cycles:
                    break
            # Pass 2: Fill remaining budget with longer cycles (4-max_length)
            if len(cycles) < max_cycles and max_length > 3:
                for cycle in nx.simple_cycles(sg, length_bound=max_length):
                    cs = frozenset(cycle)
                    if cs not in seen_sets:
                        cycles.append(cycle)
                        seen_sets.add(cs)
                    if len(cycles) >= max_cycles:
                        break
        except Exception:
            logger.warning("Cycle detection failed or timed out")
        logger.info("Cycle detection: found %d cycles", len(cycles))
        return cycles

    # ── Transaction chains ───────────────────────────────────────────

    def get_transaction_chains(self, min_hops: int = 3,
                               time_window_minutes: int = 30) -> List[List[Dict]]:
        """Extract temporal transaction chains from transactions_df directly.
        Uses the DataFrame (which has timestamps) instead of graph edge dicts
        (which omit timestamps for memory efficiency)."""
        df = self.transactions_df.copy()
        if "timestamp" not in df.columns or df.empty:
            return []

        # Sort by timestamp for temporal chain extraction
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Build adjacency: for each node, sorted list of outgoing txns
        outgoing: Dict[str, List[Dict]] = defaultdict(list)
        for _, row in df.iterrows():
            outgoing[row["source_account"]].append({
                "from": row["source_account"],
                "to": row["dest_account"],
                "amount": float(row["amount"]),
                "timestamp": row["timestamp"],
                "channel": row.get("channel", ""),
            })

        chains = []
        used_edges: Set[int] = set()  # Track used txn indices to avoid duplicates

        # Start chains from high out-degree nodes first (more likely to be chain starts)
        start_candidates = sorted(outgoing.keys(), key=lambda n: len(outgoing[n]), reverse=True)

        for start_node in start_candidates:
            if len(chains) >= 500:  # Cap total chains for performance
                break
            for start_idx, start_txn in enumerate(outgoing[start_node]):
                edge_key = (start_txn["from"], start_txn["to"], str(start_txn["timestamp"]))
                edge_hash = hash(edge_key)
                if edge_hash in used_edges:
                    continue

                chain = [start_txn]
                current_node = start_txn["to"]
                current_time = start_txn["timestamp"]
                window_end = current_time + pd.Timedelta(minutes=time_window_minutes)
                visited_in_chain = {start_txn["from"], start_txn["to"]}

                for _ in range(20):  # Max chain length
                    # Find next outgoing txn from current_node within window
                    best_next = None
                    for txn in outgoing.get(current_node, []):
                        if txn["to"] in visited_in_chain:
                            continue  # No revisiting (avoid cycles in chains)
                        if current_time <= txn["timestamp"] <= window_end:
                            best_next = txn
                            break  # Take first valid (sorted by time)
                    if best_next is None:
                        break
                    chain.append(best_next)
                    visited_in_chain.add(best_next["to"])
                    current_node = best_next["to"]
                    current_time = best_next["timestamp"]

                if len(chain) >= min_hops:
                    chains.append(chain)
                    # Mark all edges in this chain as used
                    for step in chain:
                        ek = hash((step["from"], step["to"], str(step["timestamp"])))
                        used_edges.add(ek)

        logger.info("Transaction chains: found %d chains (min_hops=%d, window=%d min)",
                    len(chains), min_hops, time_window_minutes)
        return chains

    # ── Subgraph extraction ──────────────────────────────────────────

    def get_ego_subgraph(self, account_id: str, radius: int = 2) -> nx.MultiDiGraph:
        if account_id not in self.G:
            return nx.MultiDiGraph()
        nodes = {account_id}
        frontier = {account_id}
        for _ in range(radius):
            new_frontier = set()
            for n in frontier:
                new_frontier.update(self.G.successors(n))
                new_frontier.update(self.G.predecessors(n))
            frontier = new_frontier - nodes
            nodes.update(frontier)
        return self.G.subgraph(nodes).copy()

    def get_renderable_subgraph(self, risk_scores: Dict[str, float],
                                max_nodes: int = 100) -> nx.MultiDiGraph:
        sorted_accs = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)
        seed = set()
        for acc, _ in sorted_accs:
            if acc in self.G:
                seed.add(acc)
            if len(seed) >= max_nodes // 2:
                break

        all_nodes = set(seed)
        for n in seed:
            all_nodes.update(list(self.G.successors(n))[:5])
            all_nodes.update(list(self.G.predecessors(n))[:5])

        return self.G.subgraph(list(all_nodes)[:max_nodes]).copy()

    # ── Random walk with restart ─────────────────────────────────────

    def random_walk_with_restart(self, start: str, restart_prob: float = 0.15,
                                 num_steps: int = 5000) -> Dict[str, float]:
        if start not in self.G or self.G.degree(start) == 0:
            return {}
        rng = np.random.default_rng(42)
        counts: Dict[str, int] = defaultdict(int)
        current = start
        for _ in range(num_steps):
            counts[current] += 1
            if rng.random() < restart_prob:
                current = start
                continue
            neighbors = list(self.G.successors(current)) + list(self.G.predecessors(current))
            if not neighbors:
                current = start
                continue
            current = rng.choice(neighbors)
        total = sum(counts.values())
        return {k: v / total for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True) if k != start}

    # ── Components ───────────────────────────────────────────────────

    def get_components(self) -> List[set]:
        return sorted(nx.weakly_connected_components(self.G), key=len, reverse=True)

    # ── Path ranking ─────────────────────────────────────────────────

    def rank_suspicious_paths(self, risk_scores: Dict[str, float],
                              top_n: int = 10) -> List[Dict]:
        chains = self.get_transaction_chains(min_hops=2, time_window_minutes=60)
        scored = []
        for chain in chains:
            accs = set()
            total_amt = 0
            for step in chain:
                accs.add(step["from"])
                accs.add(step["to"])
                total_amt += step.get("amount", 0)
            avg_risk = np.mean([risk_scores.get(a, 0) for a in accs])
            max_risk = max([risk_scores.get(a, 0) for a in accs])
            scored.append({
                "chain": chain, "hops": len(chain),
                "total_amount": total_amt, "accounts": list(accs),
                "avg_risk": avg_risk, "max_risk": max_risk,
                "path_score": avg_risk * 0.4 + max_risk * 0.4 + min(len(chain) / 10, 1) * 20,
            })
        scored.sort(key=lambda x: x["path_score"], reverse=True)
        return scored[:top_n]

    # ── Stats ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            "num_nodes": self.G.number_of_nodes(),
            "num_edges": self.G.number_of_edges(),
            "num_components": nx.number_weakly_connected_components(self.G),
            "density": nx.density(self.G),
            "avg_in_degree": float(np.mean([d for _, d in self.G.in_degree()])) if len(self.G) > 0 else 0,
            "avg_out_degree": float(np.mean([d for _, d in self.G.out_degree()])) if len(self.G) > 0 else 0,
        }
