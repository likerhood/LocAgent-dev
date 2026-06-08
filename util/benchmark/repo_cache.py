import contextlib
import logging
import os
import shutil
import subprocess
import uuid
from typing import Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - LocAgent benchmark runs on Linux/WSL.
    fcntl = None


logger = logging.getLogger(__name__)

REPO_CACHE_ENV = "LOCAGENT_REPO_CACHE_DIR"
REPO_CACHE_MODE_ENV = "LOCAGENT_REPO_CACHE_MODE"
REPO_CACHE_MODE_INSTANCE = "instance"
REPO_CACHE_MODE_SHARED = "shared"
REPO_CACHE_MODES = {REPO_CACHE_MODE_INSTANCE, REPO_CACHE_MODE_SHARED}

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


def repo_cache_mode() -> str:
    mode = os.environ.get(REPO_CACHE_MODE_ENV, REPO_CACHE_MODE_INSTANCE).strip()
    if mode not in REPO_CACHE_MODES:
        raise ValueError(
            f"Invalid {REPO_CACHE_MODE_ENV}={mode!r}. "
            f"Expected one of {sorted(REPO_CACHE_MODES)}."
        )
    return mode


def repo_dir_name(repo: str) -> str:
    return repo.replace("/", "_")


def cached_repo_path(cache_root: str, instance_data: dict, github_repo_path: str) -> str:
    instance_id = instance_data.get("instance_id")
    if not instance_id:
        raise ValueError("instance_data must contain 'instance_id' to use repo cache")
    return os.path.join(cache_root, instance_id, repo_dir_name(github_repo_path))


def mirror_repo_path(cache_root: str, github_repo_path: str) -> str:
    return os.path.join(cache_root, "_mirrors", f"{repo_dir_name(github_repo_path)}.git")


def shared_repo_path(cache_root: str, github_repo_path: str) -> str:
    return os.path.join(cache_root, "_shared_worktrees", repo_dir_name(github_repo_path))


def repo_lock_path(cache_root: str, github_repo_path: str) -> str:
    return os.path.join(cache_root, "_locks", f"{repo_dir_name(github_repo_path)}.lock")


def github_repo_url(github_repo_path: str) -> str:
    return f"https://github.com/{github_repo_path}.git"


def _run_command(args: list[str], cwd: Optional[str] = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _is_bare_repo_dir(repo_dir: str) -> bool:
    return (
        os.path.isfile(os.path.join(repo_dir, "HEAD"))
        and os.path.isdir(os.path.join(repo_dir, "objects"))
        and not os.path.isdir(os.path.join(repo_dir, ".git"))
    )


def _run_git(repo_dir: str, *args: str) -> str:
    if _is_bare_repo_dir(repo_dir):
        return _run_command(["git", f"--git-dir={repo_dir}", *args])
    return _run_command(["git", *args], cwd=repo_dir)


def is_git_repo(path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        return _run_git(path, "rev-parse", "--is-inside-work-tree") == "true"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_head_commit(path: str) -> str:
    return _run_git(path, "rev-parse", "HEAD")


def has_commit(repo_dir: str, commit: str) -> bool:
    if not os.path.exists(repo_dir):
        return False
    try:
        _run_git(repo_dir, "cat-file", "-e", f"{commit}^{{commit}}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _reset_cached_repo(repo_dir: str, base_commit: str) -> None:
    _run_git(repo_dir, "reset", "--hard", base_commit)
    _run_git(repo_dir, "clean", "-fd")


@contextlib.contextmanager
def repo_cache_lock(cache_root: str, github_repo_path: str):
    lock_path = repo_lock_path(cache_root, github_repo_path)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file, fcntl.LOCK_UN)


def remove_instance_cache(cache_root: str, instance_data: dict, repo_path: str) -> None:
    instance_id = instance_data.get("instance_id")
    if not instance_id:
        raise ValueError("instance_data must contain 'instance_id' to remove cached repo")

    cache_root_abs = os.path.abspath(cache_root)
    instance_dir = os.path.abspath(os.path.join(cache_root, instance_id))
    repo_path_abs = os.path.abspath(repo_path)

    if os.path.commonpath([cache_root_abs, instance_dir]) != cache_root_abs:
        raise RuntimeError(f"Refuse to delete path outside cache root: {instance_dir}")
    if os.path.commonpath([instance_dir, repo_path_abs]) != instance_dir:
        raise RuntimeError(f"Refuse to delete repo path outside instance cache: {repo_path}")

    shutil.rmtree(instance_dir, ignore_errors=True)


def _replace_dir_from_temp(tmp_path: str, final_path: str) -> None:
    if os.path.exists(final_path):
        shutil.rmtree(final_path)
    shutil.move(tmp_path, final_path)


def _clone_mirror_from_remote(github_repo_path: str, mirror_path: str) -> None:
    tmp_path = f"{mirror_path}.tmp-{uuid.uuid4()}"
    try:
        _run_command(["git", "clone", "--mirror", github_repo_url(github_repo_path), tmp_path])
        _replace_dir_from_temp(tmp_path, mirror_path)
    except Exception:
        shutil.rmtree(tmp_path, ignore_errors=True)
        raise


def _clone_mirror_from_existing_repo(source_repo_path: str, mirror_path: str) -> None:
    tmp_path = f"{mirror_path}.tmp-{uuid.uuid4()}"
    try:
        _run_command(["git", "clone", "--mirror", source_repo_path, tmp_path])
        _replace_dir_from_temp(tmp_path, mirror_path)
    except Exception:
        shutil.rmtree(tmp_path, ignore_errors=True)
        raise


def _update_mirror(mirror_path: str) -> None:
    _run_git(mirror_path, "remote", "update", "--prune")


def _find_existing_repo_with_commit(cache_root: str, github_repo_path: str, base_commit: str) -> Optional[str]:
    repo_name = repo_dir_name(github_repo_path)
    if not os.path.isdir(cache_root):
        return None

    with os.scandir(cache_root) as entries:
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.startswith("_"):
                continue
            candidate = os.path.join(entry.path, repo_name)
            if is_git_repo(candidate) and has_commit(candidate, base_commit):
                return candidate
    return None


def _ensure_mirror_repo(cache_root: str, github_repo_path: str, base_commit: str) -> str:
    mirror_path = mirror_repo_path(cache_root, github_repo_path)
    os.makedirs(os.path.dirname(mirror_path), exist_ok=True)

    if os.path.exists(mirror_path):
        if has_commit(mirror_path, base_commit):
            return mirror_path
        try:
            logger.info("Updating mirror %s for commit %s", mirror_path, base_commit)
            _update_mirror(mirror_path)
            if has_commit(mirror_path, base_commit):
                return mirror_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Broken mirror detected. Rebuilding %s", mirror_path)
        shutil.rmtree(mirror_path, ignore_errors=True)

    existing_repo = _find_existing_repo_with_commit(cache_root, github_repo_path, base_commit)
    if existing_repo:
        logger.info(
            "Bootstrapping mirror %s from existing cached repo %s",
            mirror_path,
            existing_repo,
        )
        _clone_mirror_from_existing_repo(existing_repo, mirror_path)
        if has_commit(mirror_path, base_commit):
            return mirror_path
        shutil.rmtree(mirror_path, ignore_errors=True)

    logger.info("Mirror for %s not found. Cloning into %s", github_repo_path, mirror_path)
    _clone_mirror_from_remote(github_repo_path, mirror_path)
    if not has_commit(mirror_path, base_commit):
        raise RuntimeError(
            f"Mirror {mirror_path} does not contain base commit {base_commit} "
            f"for {github_repo_path}"
        )
    return mirror_path


def _clone_instance_from_mirror(mirror_path: str, repo_path: str) -> None:
    tmp_path = f"{repo_path}.tmp-{uuid.uuid4()}"
    try:
        os.makedirs(os.path.dirname(repo_path), exist_ok=True)
        _run_command(["git", "clone", mirror_path, tmp_path])
        _replace_dir_from_temp(tmp_path, repo_path)
    except Exception:
        shutil.rmtree(tmp_path, ignore_errors=True)
        raise


def prepare_cached_repo(cache_root: str, instance_data: dict, github_repo_path: str) -> str:
    if not cache_root:
        raise ValueError("cache_root must be provided")

    base_commit = instance_data.get("base_commit")
    if not base_commit:
        raise ValueError("instance_data must contain 'base_commit' to use repo cache")

    repo_path = cached_repo_path(cache_root, instance_data, github_repo_path)

    if os.path.exists(repo_path):
        try:
            if not is_git_repo(repo_path) or not has_commit(repo_path, base_commit):
                raise RuntimeError(f"Cached repo is incomplete or missing commit: {repo_path}")
            _reset_cached_repo(repo_path, base_commit)
            logger.info("Using cached repo %s at commit %s", repo_path, base_commit)
            return repo_path
        except (RuntimeError, subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(
                "Broken cached repo for %s detected at %s. Rebuilding.",
                instance_data.get("instance_id"),
                repo_path,
            )
            remove_instance_cache(cache_root, instance_data, repo_path)

    with repo_cache_lock(cache_root, github_repo_path):
        if os.path.exists(repo_path):
            try:
                if is_git_repo(repo_path) and has_commit(repo_path, base_commit):
                    _reset_cached_repo(repo_path, base_commit)
                    logger.info("Using cached repo %s at commit %s", repo_path, base_commit)
                    return repo_path
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.warning(
                    "Broken cached repo for %s detected at %s. Rebuilding.",
                    instance_data.get("instance_id"),
                    repo_path,
                )
            remove_instance_cache(cache_root, instance_data, repo_path)

        mirror_path = _ensure_mirror_repo(cache_root, github_repo_path, base_commit)
        logger.info(
            "Cached repo for %s not found. Cloning %s from local mirror %s",
            instance_data.get("instance_id"),
            github_repo_path,
            mirror_path,
        )
        _clone_instance_from_mirror(mirror_path, repo_path)
        _reset_cached_repo(repo_path, base_commit)
        return repo_path


def _remove_shared_repo(cache_root: str, repo_path: str) -> None:
    cache_root_abs = os.path.abspath(cache_root)
    shared_root = os.path.abspath(os.path.join(cache_root, "_shared_worktrees"))
    repo_path_abs = os.path.abspath(repo_path)

    if os.path.commonpath([cache_root_abs, shared_root]) != cache_root_abs:
        raise RuntimeError(f"Refuse to delete path outside cache root: {shared_root}")
    if os.path.commonpath([shared_root, repo_path_abs]) != shared_root:
        raise RuntimeError(f"Refuse to delete shared repo outside shared cache: {repo_path}")

    shutil.rmtree(repo_path, ignore_errors=True)


def prepare_shared_repo(cache_root: str, instance_data: dict, github_repo_path: str) -> str:
    if not cache_root:
        raise ValueError("cache_root must be provided")

    base_commit = instance_data.get("base_commit")
    if not base_commit:
        raise ValueError("instance_data must contain 'base_commit' to use repo cache")

    repo_path = shared_repo_path(cache_root, github_repo_path)

    with repo_cache_lock(cache_root, github_repo_path):
        mirror_path = _ensure_mirror_repo(cache_root, github_repo_path, base_commit)

        if os.path.exists(repo_path):
            try:
                if not is_git_repo(repo_path):
                    raise RuntimeError(f"Shared repo is not a git repo: {repo_path}")
                if not has_commit(repo_path, base_commit):
                    logger.info(
                        "Shared repo %s missing commit %s. Fetching from mirror.",
                        repo_path,
                        base_commit,
                    )
                    _run_git(repo_path, "fetch", "--all", "--prune")
                if not has_commit(repo_path, base_commit):
                    raise RuntimeError(f"Shared repo is missing commit: {repo_path}")
                _reset_cached_repo(repo_path, base_commit)
                logger.info("Using shared repo %s at commit %s", repo_path, base_commit)
                return repo_path
            except (RuntimeError, subprocess.CalledProcessError, FileNotFoundError):
                logger.warning(
                    "Broken shared repo for %s detected at %s. Rebuilding.",
                    github_repo_path,
                    repo_path,
                )
                _remove_shared_repo(cache_root, repo_path)

        logger.info(
            "Shared repo for %s not found. Cloning from local mirror %s into %s",
            github_repo_path,
            mirror_path,
            repo_path,
        )
        _clone_instance_from_mirror(mirror_path, repo_path)
        _reset_cached_repo(repo_path, base_commit)
        return repo_path


def prepare_repo_from_cache(cache_root: str, instance_data: dict, github_repo_path: str) -> str:
    mode = repo_cache_mode()
    if mode == REPO_CACHE_MODE_INSTANCE:
        return prepare_cached_repo(cache_root, instance_data, github_repo_path)
    if mode == REPO_CACHE_MODE_SHARED:
        return prepare_shared_repo(cache_root, instance_data, github_repo_path)
    raise AssertionError(f"Unhandled repo cache mode: {mode}")
