import os

from datasets import load_dataset


def is_local_dataset_file(dataset_name: str) -> bool:
    return (
        isinstance(dataset_name, str)
        and os.path.isfile(dataset_name)
        and dataset_name.endswith((".jsonl", ".json"))
    )


def load_benchmark_dataset(dataset_name: str, split: str = "test"):
    if is_local_dataset_file(dataset_name):
        return load_dataset("json", data_files=dataset_name, split="train")
    return load_dataset(dataset_name, split=split)
