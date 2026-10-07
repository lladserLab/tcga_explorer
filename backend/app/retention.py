"""Explicit retention marker for local projects; null alone is not permission."""


def persistent_local_dataset(dataset) -> bool:
    return (
        dataset.visibility == "private"
        and (dataset.metadata_json or {}).get("retention_policy") == "local_until_deleted"
    )
