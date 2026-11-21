"""Reject co-author trailers and commits outside the owner's Git identity."""

import re
import subprocess
import sys


OWNER_EMAIL = "luigilaxmaster-coder@users.noreply.github.com"
OWNER_NAME = "luigilaxmaster-coder"
COAUTHOR_TRAILER = re.compile(r"^\s*co-authored-by\s*:", re.IGNORECASE | re.MULTILINE)


def validate_log(output: str) -> list[str]:
    errors = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        fields = record.strip("\n").split("\x1f", 5)
        if len(fields) != 6:
            errors.append("Malformed git log record")
            continue
        commit, author_name, author_email, committer_name, committer_email, message = fields
        if author_email.casefold() != OWNER_EMAIL.casefold() or committer_email.casefold() != OWNER_EMAIL.casefold():
            errors.append(f"{commit[:12]}: author and committer must use the repository owner's verified email")
        if author_name != OWNER_NAME or committer_name != OWNER_NAME:
            errors.append(f"{commit[:12]}: author and committer names must match the repository owner")
        if COAUTHOR_TRAILER.search(message):
            errors.append(f"{commit[:12]}: Co-authored-by trailers are prohibited")
    if not output.strip():
        errors.append("No commits were supplied for author-policy validation")
    return errors


def commit_range(base: str, head: str, default_ref: str) -> list[str]:
    if base and not re.fullmatch(r"0+", base):
        return [f"{base}..{head}"]
    if not default_ref:
        raise ValueError("A new-branch push requires the fetched default branch reference")
    common = subprocess.run(
        ["git", "merge-base", head, default_ref], check=True, capture_output=True, text=True,
    ).stdout.strip()
    resolved_head = subprocess.run(
        ["git", "rev-parse", "--verify", f"{head}^{{commit}}"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    # A branch created at the default tip still validates its tip, not unrelated history.
    return [f"{common}..{head}"] if common != resolved_head else [head, "--max-count=1"]


def main(base: str, head: str, default_ref: str = "") -> int:
    try:
        result = subprocess.run(
            ["git", "log", *commit_range(base, head, default_ref), "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Unable to inspect commit range: {exc}", file=sys.stderr)
        return 2
    errors = validate_log(result.stdout)
    if errors:
        print("Author policy failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    print("Author policy passed: owner identity only; no co-author trailers.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Usage: check_author_policy.py BASE_SHA HEAD_SHA [DEFAULT_BRANCH_REF]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(*sys.argv[1:]))
