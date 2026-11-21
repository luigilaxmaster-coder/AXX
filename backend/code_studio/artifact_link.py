"""Bidirectional Code <-> Spatial Artifact Link & External Git Push/PR Approval Gate (PR-18 / CODE-05 / E2E-05).

Enforces Invariants:
- CODE-05: Local worktree diffs and commits are permitted inside isolated agent worktrees,
  but any external remote git action ('git push', 'gh pr create', 'git push --tags') is strictly
  blocked without a verified 'write_external' human approval receipt.
- E2E-05: Links Code Studio files/changesets bidirectionally with Diagram Studio / CAD Studio
  artifacts inside SceneDocument v2.
"""
from __future__ import annotations

from typing import Any

from backend.code_studio.projects import CodeProjectService


class ExternalGitPushBlockedError(PermissionError):
    """Raised when an agent attempts git push or PR creation without an approved write_external receipt (CODE-05)."""


class CodeArtifactLinkService:
    """Links Code Studio source files and changesets with Magic Pen / Spatial Studio artifacts and gates external Git pushes."""

    def __init__(self, project_service: CodeProjectService):
        self.projects = project_service
        self.links: list[dict[str, Any]] = []
        self.approved_external_ops: dict[str, dict[str, Any]] = {}

    def link_code_to_spatial_artifact(
        self,
        *,
        project_id: str,
        relative_path: str,
        changeset_id: str,
        scene_id: str,
        spatial_object_id: str,
        artifact_kind: str = 'diagram_2d',
    ) -> dict[str, Any]:
        doc = self.projects.read_document(project_id, relative_path)
        link = {
            'link_id': f'link:{project_id}:{changeset_id}:{spatial_object_id}',
            'project_id': project_id,
            'path': relative_path,
            'file_sha256': doc['sha256'],
            'changeset_id': changeset_id,
            'scene_id': scene_id,
            'spatial_object_id': spatial_object_id,
            'artifact_kind': artifact_kind,
        }
        self.links.append(link)
        return dict(link)

    def record_external_write_approval(
        self,
        *,
        approval_operation_id: str,
        approved: bool,
        actor: str = 'user',
        scope: str = 'git_push',
    ) -> dict[str, Any]:
        entry = {
            'approval_operation_id': approval_operation_id,
            'approved': bool(approved),
            'actor': actor,
            'scope': scope,
        }
        self.approved_external_ops[approval_operation_id] = entry
        return entry

    def authorize_external_git_action(
        self,
        *,
        action: str,
        remote: str,
        branch: str,
        approval_operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Gate any external remote git push or PR creation on an explicit user approval receipt (CODE-05)."""
        if not approval_operation_id or approval_operation_id not in self.approved_external_ops:
            raise ExternalGitPushBlockedError(
                f'External git action {action!r} to {remote}/{branch} blocked (CODE-05): '
                'missing explicit write_external user approval receipt'
            )
        receipt = self.approved_external_ops[approval_operation_id]
        if not receipt.get('approved'):
            raise ExternalGitPushBlockedError(
                f'External git action {action!r} to {remote}/{branch} blocked (CODE-05): approval was denied'
            )
        return {
            'authorized': True,
            'action': action,
            'remote': remote,
            'branch': branch,
            'approval_operation_id': approval_operation_id,
        }
