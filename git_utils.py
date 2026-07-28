import os
import subprocess


DEFAULT_REPO_PATH = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.realpath(__file__)))))


def _run_git_command(*args: str, cwd: str = DEFAULT_REPO_PATH) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or f"git {' '.join(args)} failed"
        raise RuntimeError(details)
    return (result.stdout or "").strip()


def _blocking_worktree_changes(cwd: str) -> tuple[str, str, str, str]:
    """Return changes that make an automated pull unsafe.

    A submodule being checked out at a different commit than the superproject's
    gitlink is not itself unsafe: ``git submodule update`` can reconcile that
    state. Changes to files inside a submodule are still blocking.
    """
    top_level = _run_git_command(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=all",
        cwd=cwd,
    )

    # --ignore-submodules=all also hides staged gitlink changes and conflicts,
    # so check those explicitly rather than mistaking them for a harmless
    # submodule checkout mismatch.
    staged = _run_git_command("diff", "--cached", "--name-only", "HEAD", "--", cwd=cwd)
    unmerged = _run_git_command("diff", "--name-only", "--diff-filter=U", "--", cwd=cwd)

    # Check each initialized submodule from within its own worktree. Ignoring
    # nested submodules at each level is intentional: --recursive visits and
    # checks their actual worktrees separately. The cached and unmerged checks
    # catch staged nested gitlinks hidden by --ignore-submodules=all. A clean
    # mismatched commit is safe to reconcile only while a ref keeps it reachable.
    submodules = _run_git_command(
        "submodule",
        "foreach",
        "--quiet",
        "--recursive",
        (
            "git status --porcelain=v1 --untracked-files=all --ignore-submodules=all"
            " && git diff --cached --name-only HEAD --"
            " && git diff --name-only --diff-filter=U --"
            " && current=$(git rev-parse HEAD)"
            ' && if test "$current" != "$sha1"'
            ' && test -z "$(git for-each-ref --format="%(refname)" --contains HEAD)";'
            " then"
            ' printf "Submodule %s is at unreferenced commit %s\\n"'
            ' "$displaypath" "$current";'
            " fi"
        ),
        cwd=cwd,
    )
    return top_level, staged, unmerged, submodules


def _has_untracked_changes(status_output: str) -> bool:
    return any(line.startswith("?? ") for line in status_output.splitlines())


def _ignored_paths_blocking_reset(cwd: str) -> list[str]:
    """Return ignored paths that a hard reset could overwrite or remove."""
    changed_paths = {
        path.rstrip("/")
        for path in _run_git_command(
            "diff", "--name-only", "-z", "HEAD", "--", cwd=cwd
        ).split("\0")
        if path
    }
    ignored_paths = {
        path.rstrip("/")
        for path in _run_git_command(
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
            "-z",
            "--",
            cwd=cwd,
        ).split("\0")
        if path
    }

    return sorted(
        ignored
        for ignored in ignored_paths
        if any(
            ignored == changed
            or ignored.startswith(f"{changed}/")
            or changed.startswith(f"{ignored}/")
            for changed in changed_paths
        )
    )


async def safe_git_pull(cwd: str = DEFAULT_REPO_PATH, force: bool = False) -> str:
    """Safely fast-forward a repo and reconcile its pinned submodules.

    Refuses to pull if the repo has real file changes, is detached, is missing
    an upstream, is ahead of upstream, or is otherwise not in a straightforward
    fast-forward state. A clean submodule commit mismatch is reconciled to the
    commit pinned by the superproject.
    """
    try:
        inside_work_tree = _run_git_command("rev-parse", "--is-inside-work-tree", cwd=cwd)
        if inside_work_tree != "true":
            raise RuntimeError("Not inside a git worktree.")

        branch = _run_git_command("symbolic-ref", "--short", "HEAD", cwd=cwd)
        upstream = _run_git_command("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", cwd=cwd)
        if not upstream:
            raise RuntimeError("Refusing to pull: current branch has no upstream configured.")

        _run_git_command("fetch", "--prune", "--quiet", "--no-recurse-submodules", cwd=cwd)
        ahead_behind = _run_git_command("rev-list", "--left-right", "--count", "HEAD...@{u}", cwd=cwd)
        ahead_str, behind_str = ahead_behind.split()
        ahead = int(ahead_str)
        behind = int(behind_str)

        if ahead:
            raise RuntimeError(f"Refusing to pull: branch '{branch}' is ahead of '{upstream}' by {ahead} commit(s).")

        top_level, staged, unmerged, submodules = _blocking_worktree_changes(cwd)
        if any((top_level, staged, unmerged, submodules)):
            # Preserve untracked files and all changes made inside submodules,
            # even in force mode. Force only discards tracked superproject
            # changes, matching its original scope without risking nested work.
            can_reset = (
                force
                and not submodules
                and not _has_untracked_changes(top_level)
                and not _ignored_paths_blocking_reset(cwd)
            )
            if can_reset:
                _run_git_command("reset", "--hard", "HEAD", cwd=cwd)
                top_level, staged, unmerged, submodules = _blocking_worktree_changes(cwd)

            if any((top_level, staged, unmerged, submodules)):
                raise RuntimeError("Refusing to pull: worktree has uncommitted or untracked changes.")

        pull_output = ""
        if behind:
            pull_output = _run_git_command(
                "pull",
                "--ff-only",
                "--no-rebase",
                "--no-recurse-submodules",
                cwd=cwd,
            )

        sync_output = _run_git_command("submodule", "sync", "--recursive", cwd=cwd)
        submodule_output = _run_git_command(
            "submodule", "update", "--init", "--recursive", "--checkout", cwd=cwd
        )

        post_pull_changes = _run_git_command(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
            cwd=cwd,
        )
        if post_pull_changes:
            raise RuntimeError("Git pull completed but left unexpected worktree changes.")

        if pull_output:
            status_output = pull_output
        elif behind:
            status_output = f"Fast-forwarded {branch} from {upstream}."
        else:
            status_output = f"Already up to date on {branch}."
        output_parts = [part for part in [status_output, sync_output, submodule_output] if part]
        return "\n".join(output_parts)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"safe_git_pull aborted: {exc}") from exc
