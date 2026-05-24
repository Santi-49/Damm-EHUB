from services.optimizer.app.graph_builder import visualize_kmeans_segmentation
fig = visualize_kmeans_segmentation("2025-W13-7d")
fig.savefig("kmeans_seg.png", dpi=150, bbox_inches="tight")