import logging
import os
import subprocess
from typing import Optional

from util.benchmark.git_repo_manager import setup_github_repo


logger = logging.getLogger(__name__)

REPO_CACHE_ENV = "LOCAGENT_REPO_CACHE_DIR"

DATASET_CACHE_ROOTS = {
    "czlll/SWE-bench_Lite": "repo_swebenchlite",
    "princeton-nlp/SWE-bench_Lite": "repo_swebenchlite",
    "czlll/Loc-Bench_V1": "repo_locbench",
}


def cache_root_for_dataset(dataset: Optional[str]) -> Optional[str]:
    env_cache_root = os.environ.get(REPO_CACHE_ENV)
    if env_cache_root:
        return env_cache_root
    if not dataset:
        return None
    return DATASET_CACHE_ROOTS.get(dataset)


def repo_dir_name(repo: str) -> str:
    return repo.replace("/", "_")


def cached_repo_path(cache_root: str, instance_data: dict, github_repo_path: str) -> str:
    instance_id = instance_data.get("instance_id")
    if not instance_id:
        raise ValueError("instance_data must contain 'instance_id' to use repo cache")
    return os.path.join(cache_root, instance_id, repo_dir_name(github_repo_path))


def _run_git(repo_dir: str, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def is_git_repo(path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        return _run_git(path, "rev-parse", "--is-inside-work-tree") == "true"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_head_commit(path: str) -> str:
    return _run_git(path, "rev-parse", "HEAD")


def _reset_cached_repo(repo_dir: str, base_commit: str) -> None:
    _run_git(repo_dir, "reset", "--hard", base_commit)
    _run_git(repo_dir, "clean", "-fd")


def prepare_cached_repo(cache_root: str, instance_data: dict, github_repo_path: str) -> str:
    if not cache_root:
        raise ValueError("cache_root must be provided")

    base_commit = instance_data.get("base_commit")
    if not base_commit:
        raise ValueError("instance_data must contain 'base_commit' to use repo cache")

    repo_path = cached_repo_path(cache_root, instance_data, github_repo_path)
    instance_cache_dir = os.path.dirname(repo_path)

    if os.path.exists(repo_path):
        if not is_git_repo(repo_path):
            raise RuntimeError(f"Cached repo path exists but is not a git repo: {repo_path}")
        _reset_cached_repo(repo_path, base_commit)
        logger.info("Using cached repo %s at commit %s", repo_path, base_commit)
        return repo_path

    os.makedirs(instance_cache_dir, exist_ok=True)
    logger.info(
        "Cached repo for %s not found. Cloning %s into %s",
        instance_data.get("instance_id"),
        github_repo_path,
        instance_cache_dir,
    )
    return setup_github_repo(
        repo=github_repo_path,
        base_commit=base_commit,
        base_dir=instance_cache_dir,
    )
