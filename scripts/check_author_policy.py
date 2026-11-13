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


def main(base: str, head: str) -> int:
    try:
        result = subprocess.run(
            ["git", "log", f"{base}..{head}", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Unable to inspect commit range: {exc}", file=sys.stderr)
        return 2
    errors = validate_log(result.stdout)
    if errors:
        print("Author policy failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    print("Author policy passed: owner identity only; no co-author trailers.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: check_author_policy.py BASE_SHA HEAD_SHA", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
