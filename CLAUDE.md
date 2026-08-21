<!-- BEGIN KNOWLEDGEBASE AGENT BRIDGE (managed) -->
# KnowledgeBase project bridge

- Tool: Claude Code
- Resolve the KnowledgeBase at `%USERPROFILE%\OneDrive\ドキュメント\KnowledgeBase`, verified by the six Vault markers.
- Resolve the Projects root at `%USERPROFILE%\dev\Projects`; code must remain outside OneDrive.
- Workspace relative to Projects root: `enja-reader`
- Expected resolved workspace: `%USERPROFILE%\dev\Projects\enja-reader`
- Before inspecting project files, resolve the current working directory and confirm it is this expected workspace or its descendant.
- If the current path is under OneDrive Projects, points at a same-named stale folder, or differs from the expected workspace, stop with `WRONG_WORKSPACE`. Do not report files as deleted and do not perform a broad search until the path mismatch is reported.
- Canonical project context relative to the resolved Vault: `90_Projects/enja-reader/agent_context.md`
- Before substantial project work, read the canonical project context and the shared bootstrap memory.
- Keep code, tests, Git state, and generated artifacts in this workspace.
- Write durable decisions, failed approaches, current state, and next actions back to the canonical project context.
- Do not copy secrets, private datasets, credentials, or verbose reasoning into the Vault.
- If the KnowledgeBase is not accessible, report the missing additional-directory permission instead of treating auto-memory as canonical.
<!-- END KNOWLEDGEBASE AGENT BRIDGE (managed) -->
