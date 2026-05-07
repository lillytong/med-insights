"""
Clustering step for med-insights.

Pulls all embeddings from ChromaDB, discovers natural clusters with HDBSCAN,
reduces to 2D with UMAP for visualization, then labels each cluster with
a 3-5 word theme via Sonnet.

Cluster labels + 2D coordinates are written back into ChromaDB metadata so
the dashboard can read them directly.

Returns a list of ClusterResult objects for the dashboard to render.
"""

import json
from dataclasses import dataclass, field

import anthropic
import numpy as np

import config


@dataclass
class ClusterResult:
    cluster_id: int           # -1 = noise (HDBSCAN outliers)
    label: str                # Sonnet-generated theme, e.g. "Prior auth blocking biologics"
    post_ids: list[str] = field(default_factory=list)
    dominant_sentiment: str = ""
    communities: list[str] = field(default_factory=list)   # unique communities present
    top_unmet_needs: list[str] = field(default_factory=list)
    post_count: int = 0
    # 2D centroid for dashboard bubble placement
    x: float = 0.0
    y: float = 0.0


def _fetch_all(collection) -> tuple[list[str], np.ndarray, list[dict]]:
    """Pull every record from ChromaDB. Returns (ids, embeddings_array, metadatas)."""
    total = collection.count()
    if total == 0:
        return [], np.array([]), []

    results = collection.get(include=["embeddings", "metadatas", "documents"])
    ids = results["ids"]
    embeddings = np.array(results["embeddings"], dtype=np.float32)
    metadatas = results["metadatas"]
    documents = results["documents"]
    return ids, embeddings, metadatas, documents


def _label_cluster(cluster_docs: list[str], client: anthropic.Anthropic) -> str:
    """Ask Sonnet to generate a 3-5 word theme label for a cluster's documents."""
    sample = cluster_docs[:12]   # cap context — labels don't need the full cluster
    joined = "\n---\n".join(sample)

    response = client.messages.create(
        model=config.SONNET_MODEL,
        max_tokens=40,
        messages=[{
            "role": "user",
            "content": (
                "These are summaries from a cluster of physician forum threads. "
                "Give me a 3-5 word theme label that captures the shared clinical problem. "
                "Reply with ONLY the label — no punctuation, no explanation.\n\n"
                f"{joined}"
            ),
        }],
    )
    return response.content[0].text.strip()


def cluster(min_cluster_size: int = 5) -> list[ClusterResult]:
    """
    Main entry point.

    Args:
        min_cluster_size: HDBSCAN minimum posts to form a cluster (default 5).
                          Lower = more clusters. Raise if you want fewer, broader themes.

    Returns list of ClusterResult (noise cluster omitted if empty).
    """
    try:
        import hdbscan
        import umap
    except ImportError:
        raise ImportError(
            "Clustering requires hdbscan and umap-learn. "
            "Run: pip install hdbscan umap-learn"
        )

    import chromadb
    client_chroma = chromadb.PersistentClient(path=config.CHROMA_DIR)
    collection = client_chroma.get_or_create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    total = collection.count()
    if total == 0:
        print("  [clusterer] ChromaDB is empty — nothing to cluster")
        return []

    print(f"  [clusterer] fetching {total} records from ChromaDB...")
    ids, embeddings, metadatas, documents = _fetch_all(collection)

    # --- UMAP: 384 dims → 2D ---
    print(f"  [clusterer] UMAP: {embeddings.shape[1]} → 2D...")
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(15, total - 1),
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    coords_2d = reducer.fit_transform(embeddings)   # shape (N, 2)

    # --- HDBSCAN clustering ---
    print(f"  [clusterer] HDBSCAN (min_cluster_size={min_cluster_size})...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        metric="euclidean",   # on UMAP-reduced 2D space
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(coords_2d)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    print(f"  [clusterer] {n_clusters} clusters found, {n_noise} noise points")

    # --- Build per-cluster data ---
    from collections import Counter

    cluster_map: dict[int, dict] = {}
    for i, (pid, meta, doc) in enumerate(zip(ids, metadatas, documents)):
        cid = int(labels[i])
        if cid not in cluster_map:
            cluster_map[cid] = {
                "post_ids": [],
                "docs": [],
                "sentiments": [],
                "communities": [],
                "unmet_needs": [],
                "coords": [],
            }
        cluster_map[cid]["post_ids"].append(pid)
        cluster_map[cid]["docs"].append(doc)
        cluster_map[cid]["sentiments"].append(meta.get("sentiment", ""))
        cluster_map[cid]["communities"].append(meta.get("community", ""))
        cluster_map[cid]["unmet_needs"].append(meta.get("unmet_need", ""))
        cluster_map[cid]["coords"].append(coords_2d[i])

    # --- Label clusters with Sonnet ---
    anthropic_client = anthropic.Anthropic()
    results: list[ClusterResult] = []

    for cid in sorted(cluster_map.keys()):
        data = cluster_map[cid]
        coords_arr = np.array(data["coords"])
        centroid = coords_arr.mean(axis=0)

        if cid == -1:
            label = "Noise / uncategorized"
        else:
            print(f"  [clusterer] labeling cluster {cid} ({len(data['post_ids'])} posts)...")
            label = _label_cluster(data["docs"], anthropic_client)

        dominant_sentiment = Counter(data["sentiments"]).most_common(1)[0][0]
        unique_communities = sorted(set(data["communities"]))
        top_needs = [
            n for n in data["unmet_needs"]
            if n.lower() not in ("none identified", "none", "n/a", "")
        ][:5]

        results.append(ClusterResult(
            cluster_id=cid,
            label=label,
            post_ids=data["post_ids"],
            dominant_sentiment=dominant_sentiment,
            communities=unique_communities,
            top_unmet_needs=top_needs,
            post_count=len(data["post_ids"]),
            x=float(centroid[0]),
            y=float(centroid[1]),
        ))

    # --- Write cluster_id + 2D coords back to ChromaDB metadata ---
    print("  [clusterer] writing cluster assignments back to ChromaDB...")
    update_ids, update_metadatas = [], []
    for i, pid in enumerate(ids):
        new_meta = dict(metadatas[i])
        new_meta["cluster_id"] = int(labels[i])
        new_meta["umap_x"] = float(coords_2d[i][0])
        new_meta["umap_y"] = float(coords_2d[i][1])
        update_ids.append(pid)
        update_metadatas.append(new_meta)

    # ChromaDB update in batches of 500 to stay under limits
    batch = 500
    for start in range(0, len(update_ids), batch):
        collection.update(
            ids=update_ids[start:start + batch],
            metadatas=update_metadatas[start:start + batch],
        )

    print(f"  [clusterer] done — {len(results)} clusters (including noise)")
    return results
