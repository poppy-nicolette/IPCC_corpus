#verify_bc_cc.py
"""
Sparse correctness oracle for bibliographic coupling (BC) and co-citation (CC).

Independent reimplementation of biblionet's net_bc() / net_cc() using sparse
matrix algebra, used to validate those methods before any rebuild.

Formulation (A[i,k] = 1 means work i cites work k):
    BC = A . A^T   (two works weighted by shared references)
    CC = A^T . A   (two works weighted by shared citers)
Restrict to the core work universe, drop the diagonal (self counts, not edges),
keep the upper triangle (undirected dedup, source id < target id).

Usage:
    # No arguments: validate the sample fixtures against the committed sample
    # networks. Paths are resolved relative to THIS file, so it runs from anywhere.
    #   works=../data/works.csv  citations=../data/citations.csv  networks=../networks
    python verify_bc_cc.py

    # Explicit paths (use this for the full-scale data):
    python verify_bc_cc.py WORKS CITATIONS NETWORKS_DIR
"""
import os
import sys
import numpy as np
import pandas as pd
import scipy.sparse as sp


def build_edges(works_file, citations_file):
    works = pd.read_csv(works_file)
    cits = pd.read_csv(citations_file)

    core_ids = works['id'].astype(int).to_numpy()

    citing = cits['citing_id'].astype(int).to_numpy()
    cited = cits['cited_id'].astype(int).to_numpy()

    # Global contiguous index over every id that appears (citing, cited, or core).
    all_ids = np.unique(np.concatenate([citing, cited, core_ids]))
    pos = {wid: i for i, wid in enumerate(all_ids)}
    n = all_ids.size

    rows = np.fromiter((pos[w] for w in citing), dtype=np.int64, count=citing.size)
    cols = np.fromiter((pos[w] for w in cited), dtype=np.int64, count=cited.size)
    data = np.ones(rows.size, dtype=np.int64)

    # A: rows = citing work, cols = cited work. Dedup repeated (citing,cited) to 1.
    A = sp.csr_matrix((data, (rows, cols)), shape=(n, n))
    A.data[:] = 1
    A.sum_duplicates()
    A.data[:] = 1

    core_idx = np.fromiter((pos[w] for w in core_ids), dtype=np.int64, count=core_ids.size)

    # BC = A_core . A_core^T  (shared references among core works)
    A_core_rows = A[core_idx, :]
    bc = (A_core_rows @ A_core_rows.T).tocoo()

    # CC = A[:,core]^T . A[:,core]  (shared citers among core works)
    A_core_cols = A[:, core_idx]
    cc = (A_core_cols.T @ A_core_cols).tocoo()

    return _to_edge_df(bc, core_ids), _to_edge_df(cc, core_ids)


def _to_edge_df(mat, core_ids):
    """COO core-by-core matrix -> source<target edge list with integer ids."""
    s_id = core_ids[mat.row]
    t_id = core_ids[mat.col]
    keep = s_id < t_id              # upper triangle by id; also drops the diagonal
    df = pd.DataFrame({
        'source': s_id[keep],
        'target': t_id[keep],
        'weight': mat.data[keep].astype(int),
    })
    return df.sort_values(['source', 'target']).reset_index(drop=True)


def _canonical(df):
    """Undirected edges: orient each row so source < target by integer id.

    BC and CC are undirected, so which endpoint is stored as 'source' carries no
    meaning -- {a,b} and {b,a} are the same edge. But different producers order
    them differently: the originally committed networks ordered the pair while the
    ids were still strings ("100" < "99" lexicographically), whereas this oracle
    orders numerically. Comparing raw (source, target) tuples would therefore report
    thousands of "mismatches" that are nothing but storage order.

    Applying this to BOTH sides before comparing makes the check test what actually
    matters -- the undirected edge set and its weights -- and not an artifact of how
    each side happened to write its rows. It only swaps source/target within a row:
    no edge is added, dropped, merged, or reweighted, so it cannot mask a real
    difference.
    """
    s = df[['source', 'target', 'weight']].astype({'source': int, 'target': int, 'weight': int}).copy()
    lo = s[['source', 'target']].min(axis=1)
    hi = s[['source', 'target']].max(axis=1)
    s['source'], s['target'] = lo, hi
    return s.sort_values(['source', 'target']).reset_index(drop=True)


def compare(name, oracle, committed_file):
    oracle = _canonical(oracle)
    com = _canonical(pd.read_csv(committed_file))

    print(f"\n=== {name} ===")
    print(f"  oracle:    {len(oracle):>8} edges, weight sum {oracle['weight'].sum():>10}")
    print(f"  committed: {len(com):>8} edges, weight sum {com['weight'].sum():>10}")

    merged = oracle.merge(com, on=['source', 'target'], how='outer',
                          suffixes=('_oracle', '_committed'), indicator=True)
    only_oracle = (merged['_merge'] == 'left_only').sum()
    only_com = (merged['_merge'] == 'right_only').sum()
    both = merged[merged['_merge'] == 'both']
    weight_mismatch = (both['weight_oracle'] != both['weight_committed']).sum()

    ok = (only_oracle == 0 and only_com == 0 and weight_mismatch == 0)
    if ok:
        print(f"  MATCH: identical edge set and weights.")
    else:
        print(f"  MISMATCH: oracle-only={only_oracle} committed-only={only_com} "
              f"weight-diff={weight_mismatch}")
    return ok


def main():
    if len(sys.argv) >= 4:
        works_file, citations_file, net_dir = sys.argv[1:4]
    else:
        #Defaults are anchored to THIS file's location, not the current working
        #directory, so the no-argument form works from anywhere. This module lives in
        #Corpus/networks/Biblionet/, so '..' is Corpus/networks/: the sample fixtures
        #are in ../data and the committed sample networks are in ../networks.
        here = os.path.dirname(os.path.abspath(__file__))
        works_file     = os.path.join(here, "..", "data", "works.csv")
        citations_file = os.path.join(here, "..", "data", "citations.csv")
        net_dir        = os.path.join(here, "..", "networks")

    bc, cc = build_edges(works_file, citations_file)
    ok_bc = compare("BC", bc, os.path.join(net_dir, "net_bc.csv"))
    ok_cc = compare("CC", cc, os.path.join(net_dir, "net_cc.csv"))

    print()
    if ok_bc and ok_cc:
        print("ALL CHECKS PASSED — sparse oracle reproduces committed BC and CC.")
        return 0
    print("CHECKS FAILED.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
