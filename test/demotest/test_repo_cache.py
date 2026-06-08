import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from util.benchmark import repo_cache
from util.benchmark import setup_repo as setup_repo_module
from plugins.location_tools.repo_ops import repo_ops


def run_git(repo_dir, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def init_repo(repo_dir: Path):
    repo_dir.mkdir(parents=True)
    run_git(repo_dir, "init")
    run_git(repo_dir, "config", "user.email", "test@example.com")
    run_git(repo_dir, "config", "user.name", "Repo Cache Test")
    (repo_dir / "tracked.txt").write_text("first\n", encoding="utf-8")
    run_git(repo_dir, "add", "tracked.txt")
    run_git(repo_dir, "commit", "-m", "first")
    first_commit = run_git(repo_dir, "rev-parse", "HEAD")
    (repo_dir / "tracked.txt").write_text("second\n", encoding="utf-8")
    run_git(repo_dir, "commit", "-am", "second")
    second_commit = run_git(repo_dir, "rev-parse", "HEAD")
    return first_commit, second_commit


def init_bare_mirror(source_repo: Path, mirror_repo: Path):
    mirror_repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--mirror", str(source_repo), str(mirror_repo)],
        check=True,
        text=True,
        capture_output=True,
    )


class RepoCacheTests(unittest.TestCase):
    def test_cache_root_for_dataset_maps_supported_datasets(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(repo_cache.cache_root_for_dataset("czlll/SWE-bench_Lite"), "repo_swebenchlite")
            self.assertEqual(repo_cache.cache_root_for_dataset("princeton-nlp/SWE-bench_Lite"), "repo_swebenchlite")
            self.assertEqual(repo_cache.cache_root_for_dataset("czlll/Loc-Bench_V1"), "repo_locbench")
            self.assertIsNone(repo_cache.cache_root_for_dataset("unknown/dataset"))
            self.assertIsNone(repo_cache.cache_root_for_dataset(None))

    def test_cache_root_for_dataset_prefers_environment_override(self):
        with mock.patch.dict(os.environ, {"LOCAGENT_REPO_CACHE_DIR": "/tmp/custom-cache"}, clear=True):
            self.assertEqual(repo_cache.cache_root_for_dataset("czlll/SWE-bench_Lite"), "/tmp/custom-cache")
            self.assertEqual(repo_cache.cache_root_for_dataset(None), "/tmp/custom-cache")

    def test_cached_repo_path_uses_instance_id_and_repo_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = {
                "instance_id": "astropy__astropy-12907",
                "repo": "astropy/astropy",
                "base_commit": "abc123",
            }

            path = repo_cache.cached_repo_path(tmp, instance, "astropy/astropy")

            self.assertEqual(path, os.path.join(tmp, "astropy__astropy-12907", "astropy_astropy"))

    def test_mirror_repo_path_uses_repo_name(self):
        path = repo_cache.mirror_repo_path("repo_swebenchlite", "django/django")

        self.assertEqual(path, os.path.join("repo_swebenchlite", "_mirrors", "django_django.git"))

    def test_shared_repo_path_uses_repo_name(self):
        path = repo_cache.shared_repo_path("repo_swebenchlite", "django/django")

        self.assertEqual(path, os.path.join("repo_swebenchlite", "_shared_worktrees", "django_django"))

    def test_repo_cache_mode_defaults_to_instance(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(repo_cache.repo_cache_mode(), repo_cache.REPO_CACHE_MODE_INSTANCE)

    def test_repo_cache_mode_reads_environment(self):
        with mock.patch.dict(os.environ, {"LOCAGENT_REPO_CACHE_MODE": "shared"}, clear=True):
            self.assertEqual(repo_cache.repo_cache_mode(), repo_cache.REPO_CACHE_MODE_SHARED)

    def test_repo_cache_mode_rejects_invalid_environment(self):
        with mock.patch.dict(os.environ, {"LOCAGENT_REPO_CACHE_MODE": "other"}, clear=True):
            with self.assertRaises(ValueError):
                repo_cache.repo_cache_mode()

    def test_has_commit_returns_true_only_when_commit_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "source"
            first_commit, _ = init_repo(repo_dir)

            self.assertTrue(repo_cache.has_commit(str(repo_dir), first_commit))
            self.assertFalse(repo_cache.has_commit(str(repo_dir), "0" * 40))

    def test_prepare_cached_repo_resets_existing_repo_to_base_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = {
                "instance_id": "astropy__astropy-12907",
                "repo": "astropy/astropy",
                "base_commit": "",
            }
            repo_dir = Path(repo_cache.cached_repo_path(tmp, instance, "astropy/astropy"))
            first_commit, second_commit = init_repo(repo_dir)
            instance["base_commit"] = first_commit
            (repo_dir / "untracked.txt").write_text("temporary\n", encoding="utf-8")

            with mock.patch.object(repo_cache, "_clone_mirror_from_remote", side_effect=AssertionError("should reuse cache")):
                result = repo_cache.prepare_cached_repo(tmp, instance, "astropy/astropy")

            self.assertEqual(result, str(repo_dir))
            self.assertEqual(repo_cache.get_head_commit(result), first_commit)
            self.assertNotEqual(first_commit, second_commit)
            self.assertFalse((repo_dir / "untracked.txt").exists())
            self.assertEqual((repo_dir / "tracked.txt").read_text(encoding="utf-8"), "first\n")

    def test_prepare_cached_repo_clones_missing_repo_from_existing_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_repo = Path(tmp) / "source"
            first_commit, _ = init_repo(source_repo)
            instance = {
                "instance_id": "django__django-11039",
                "repo": "django/django",
                "base_commit": first_commit,
            }
            mirror_repo = Path(repo_cache.mirror_repo_path(tmp, "django/django"))
            init_bare_mirror(source_repo, mirror_repo)

            result = repo_cache.prepare_cached_repo(tmp, instance, "django/django")

            self.assertEqual(result, repo_cache.cached_repo_path(tmp, instance, "django/django"))
            self.assertEqual(repo_cache.get_head_commit(result), first_commit)
            self.assertEqual((Path(result) / "tracked.txt").read_text(encoding="utf-8"), "first\n")

    def test_prepare_cached_repo_rebuilds_broken_existing_repo_from_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_repo = Path(tmp) / "source"
            first_commit, _ = init_repo(source_repo)
            instance = {
                "instance_id": "django__django-13660",
                "repo": "django/django",
                "base_commit": first_commit,
            }
            mirror_repo = Path(repo_cache.mirror_repo_path(tmp, "django/django"))
            init_bare_mirror(source_repo, mirror_repo)
            broken_repo = Path(repo_cache.cached_repo_path(tmp, instance, "django/django"))
            broken_repo.mkdir(parents=True)
            (broken_repo / "partial-file").write_text("clone was interrupted\n", encoding="utf-8")

            result = repo_cache.prepare_cached_repo(tmp, instance, "django/django")

            self.assertEqual(result, str(broken_repo))
            self.assertEqual(repo_cache.get_head_commit(result), first_commit)
            self.assertFalse((broken_repo / "partial-file").exists())

    def test_prepare_cached_repo_creates_mirror_once_then_reuses_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_repo = Path(tmp) / "source"
            first_commit, _ = init_repo(source_repo)
            instance = {
                "instance_id": "django__django-13158",
                "repo": "django/django",
                "base_commit": first_commit,
            }
            clone_calls = []

            def fake_clone_mirror_from_remote(github_repo_path, mirror_path):
                clone_calls.append((github_repo_path, mirror_path))
                init_bare_mirror(source_repo, Path(mirror_path))

            with mock.patch.object(repo_cache, "_clone_mirror_from_remote", side_effect=fake_clone_mirror_from_remote):
                result = repo_cache.prepare_cached_repo(tmp, instance, "django/django")

            self.assertEqual(repo_cache.get_head_commit(result), first_commit)
            self.assertEqual(clone_calls, [("django/django", repo_cache.mirror_repo_path(tmp, "django/django"))])

            second_instance = {
                "instance_id": "django__django-13159",
                "repo": "django/django",
                "base_commit": first_commit,
            }
            with mock.patch.object(repo_cache, "_clone_mirror_from_remote", side_effect=AssertionError("mirror should be reused")):
                second_result = repo_cache.prepare_cached_repo(tmp, second_instance, "django/django")

            self.assertEqual(repo_cache.get_head_commit(second_result), first_commit)

    def test_prepare_cached_repo_bootstraps_mirror_from_existing_instance_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing_instance = {
                "instance_id": "django__django-existing",
                "repo": "django/django",
                "base_commit": "",
            }
            existing_repo = Path(repo_cache.cached_repo_path(tmp, existing_instance, "django/django"))
            first_commit, _ = init_repo(existing_repo)
            new_instance = {
                "instance_id": "django__django-new",
                "repo": "django/django",
                "base_commit": first_commit,
            }

            with mock.patch.object(repo_cache, "_clone_mirror_from_remote", side_effect=AssertionError("should use existing local repo")):
                result = repo_cache.prepare_cached_repo(tmp, new_instance, "django/django")

            self.assertTrue(Path(repo_cache.mirror_repo_path(tmp, "django/django")).exists())
            self.assertEqual(repo_cache.get_head_commit(result), first_commit)
            self.assertEqual((Path(result) / "tracked.txt").read_text(encoding="utf-8"), "first\n")

    def test_prepare_shared_repo_reuses_one_worktree_and_resets_between_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_repo = Path(tmp) / "source"
            first_commit, second_commit = init_repo(source_repo)
            mirror_repo = Path(repo_cache.mirror_repo_path(tmp, "sympy/sympy"))
            init_bare_mirror(source_repo, mirror_repo)

            first_instance = {
                "instance_id": "sympy__sympy-1",
                "repo": "sympy/sympy",
                "base_commit": first_commit,
            }
            second_instance = {
                "instance_id": "sympy__sympy-2",
                "repo": "sympy/sympy",
                "base_commit": second_commit,
            }

            first_result = repo_cache.prepare_shared_repo(tmp, first_instance, "sympy/sympy")
            self.assertEqual(first_result, repo_cache.shared_repo_path(tmp, "sympy/sympy"))
            self.assertEqual(repo_cache.get_head_commit(first_result), first_commit)
            self.assertEqual((Path(first_result) / "tracked.txt").read_text(encoding="utf-8"), "first\n")
            (Path(first_result) / "untracked.txt").write_text("temporary\n", encoding="utf-8")

            second_result = repo_cache.prepare_shared_repo(tmp, second_instance, "sympy/sympy")

            self.assertEqual(second_result, first_result)
            self.assertEqual(repo_cache.get_head_commit(second_result), second_commit)
            self.assertEqual((Path(second_result) / "tracked.txt").read_text(encoding="utf-8"), "second\n")
            self.assertFalse((Path(second_result) / "untracked.txt").exists())
            self.assertFalse(Path(repo_cache.cached_repo_path(tmp, first_instance, "sympy/sympy")).exists())
            self.assertFalse(Path(repo_cache.cached_repo_path(tmp, second_instance, "sympy/sympy")).exists())

    def test_prepare_shared_repo_rebuilds_broken_worktree_from_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_repo = Path(tmp) / "source"
            first_commit, _ = init_repo(source_repo)
            mirror_repo = Path(repo_cache.mirror_repo_path(tmp, "django/django"))
            init_bare_mirror(source_repo, mirror_repo)
            shared_repo = Path(repo_cache.shared_repo_path(tmp, "django/django"))
            shared_repo.mkdir(parents=True)
            (shared_repo / "partial-file").write_text("clone was interrupted\n", encoding="utf-8")
            instance = {
                "instance_id": "django__django-1",
                "repo": "django/django",
                "base_commit": first_commit,
            }

            result = repo_cache.prepare_shared_repo(tmp, instance, "django/django")

            self.assertEqual(result, str(shared_repo))
            self.assertEqual(repo_cache.get_head_commit(result), first_commit)
            self.assertFalse((shared_repo / "partial-file").exists())

    def test_prepare_repo_from_cache_dispatches_to_shared_mode(self):
        instance = {
            "instance_id": "django__django-1",
            "repo": "django/django",
            "base_commit": "abc123",
        }

        with mock.patch.dict(os.environ, {"LOCAGENT_REPO_CACHE_MODE": "shared"}, clear=True), \
                mock.patch.object(repo_cache, "prepare_shared_repo", return_value="/shared/repo") as shared, \
                mock.patch.object(repo_cache, "prepare_cached_repo", side_effect=AssertionError("should not use instance mode")):
            result = repo_cache.prepare_repo_from_cache("cache-root", instance, "django/django")

        self.assertEqual(result, "/shared/repo")
        shared.assert_called_once_with("cache-root", instance, "django/django")

    def test_remove_instance_cache_refuses_to_delete_outside_cache_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp).parent / "outside-repo-cache-test"
            outside.mkdir(exist_ok=True)
            try:
                instance = {
                    "instance_id": "..",
                    "repo": "django/django",
                    "base_commit": "abc123",
                }

                with self.assertRaises(RuntimeError):
                    repo_cache.remove_instance_cache(tmp, instance, str(outside))
            finally:
                shutil.rmtree(outside, ignore_errors=True)

    def test_setup_repo_uses_dataset_cache_when_supported(self):
        instance = {
            "instance_id": "astropy__astropy-12907",
            "repo": "astropy/astropy",
            "base_commit": "abc123",
        }

        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(setup_repo_module, "prepare_repo_from_cache", return_value="repo_swebenchlite/astropy__astropy-12907/astropy_astropy") as prepare, \
                mock.patch.object(setup_repo_module, "setup_github_repo", side_effect=AssertionError("should use cache")):
            result = setup_repo_module.setup_repo(
                instance_data=instance,
                repo_base_dir="playground/not-used",
                dataset="czlll/SWE-bench_Lite",
                split="test",
            )

        self.assertEqual(result, "repo_swebenchlite/astropy__astropy-12907/astropy_astropy")
        prepare.assert_called_once_with("repo_swebenchlite", instance, "astropy/astropy")

    def test_setup_repo_falls_back_to_original_clone_when_cache_not_enabled(self):
        instance = {
            "instance_id": "custom__project-1",
            "repo": "custom/project",
            "base_commit": "abc123",
        }

        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(setup_repo_module, "prepare_repo_from_cache", side_effect=AssertionError("cache should be disabled")), \
                mock.patch.object(setup_repo_module, "setup_github_repo", return_value="/tmp/repos/custom_project") as clone:
            result = setup_repo_module.setup_repo(
                instance_data=instance,
                repo_base_dir="/tmp/repos",
                dataset="custom/Dataset",
                split="test",
            )

        self.assertEqual(result, "/tmp/repos/custom_project")
        clone.assert_called_once_with(repo="custom/project", base_commit="abc123", base_dir="/tmp/repos")

    def test_reset_current_issue_deletes_only_playground_temp_dir(self):
        repo_ops.CURRENT_ISSUE_ID = "astropy__astropy-12907"
        repo_ops.CURRENT_INSTANCE = {"instance_id": "astropy__astropy-12907"}
        repo_ops.CURRENT_DATASET = "czlll/SWE-bench_Lite"
        repo_ops.CURRENT_SPLIT = "test"
        repo_ops.ALL_FILE = ["a.py"]
        repo_ops.ALL_CLASS = []
        repo_ops.ALL_FUNC = []
        repo_ops.REPO_SAVE_DIR = os.path.join("playground", "temporary-run")

        with mock.patch.object(repo_ops.subprocess, "run") as run:
            repo_ops.reset_current_issue()

        run.assert_called_once_with(["rm", "-rf", os.path.join("playground", "temporary-run")], check=True)
        self.assertIsNone(repo_ops.CURRENT_ISSUE_ID)
        self.assertIsNone(repo_ops.CURRENT_INSTANCE)
        self.assertIsNone(repo_ops.CURRENT_DATASET)
        self.assertIsNone(repo_ops.CURRENT_SPLIT)
        self.assertIsNone(repo_ops.REPO_SAVE_DIR)

    def test_reset_current_issue_does_not_delete_fixed_cache_dir(self):
        repo_ops.REPO_SAVE_DIR = os.path.join("repo_swebenchlite", "astropy__astropy-12907", "astropy_astropy")

        with mock.patch.object(repo_ops.subprocess, "run") as run:
            repo_ops.reset_current_issue()

        run.assert_not_called()
        self.assertIsNone(repo_ops.REPO_SAVE_DIR)

    def test_set_current_issue_does_not_create_playground_when_graph_index_exists(self):
        instance = {
            "instance_id": "astropy__astropy-12907",
            "repo": "astropy/astropy",
            "base_commit": "abc123",
        }
        fake_entity_searcher = mock.Mock()
        fake_entity_searcher.get_all_nodes_by_type.return_value = []

        def fake_exists(path):
            return str(path).endswith(".pkl")

        repo_ops.REPO_SAVE_DIR = None
        with mock.patch.object(repo_ops.os.path, "exists", side_effect=fake_exists), \
                mock.patch.object(repo_ops.os, "makedirs") as makedirs, \
                mock.patch("builtins.open", mock.mock_open()), \
                mock.patch.object(repo_ops.pickle, "load", return_value=object()), \
                mock.patch.object(repo_ops, "RepoEntitySearcher", return_value=fake_entity_searcher), \
                mock.patch.object(repo_ops, "RepoDependencySearcher"), \
                mock.patch.object(repo_ops, "setup_repo") as setup_repo:
            repo_ops.set_current_issue(
                instance_data=instance,
                dataset="czlll/SWE-bench_Lite",
                split="test",
                rank=0,
            )

        makedirs.assert_not_called()
        setup_repo.assert_not_called()
        self.assertIsNone(repo_ops.REPO_SAVE_DIR)


if __name__ == "__main__":
    unittest.main()
