# Technical evidence checked during design

These sources establish product behavior, not an implemented or connected system.

1. CockroachDB row-level security: https://docs.cockroachlabs.com/docs/stable/row-level-security (checked 2 October 2026). RLS complements SQL grants. Administrative roles and owners can bypass protections; owner enforcement and least-privilege roles must be verified. View privilege semantics need explicit testing. RLS does not protect all export/replication paths. The MVP should grant access only through authorized service methods and restricted database identities and test agent A vs agent B.
2. CockroachDB transaction retry reference: https://docs.cockroachlabs.com/docs/stable/transaction-retry-error-reference (checked 2 October 2026). Under SERIALIZABLE, a client may need to replay a complete transaction on SQLSTATE 40001. Keep LLM calls and external side effects outside retried transactions; use a bounded retry budget and an idempotency key for approval requests.
3. Feature Dev cached local README and agents/code-architect.md. Session loading is supported by the installed Claude Code CLI's --plugin-dir option. No global plugin installation is necessary.

## Integration state
- Claude Code authenticated. Requested model: claude-opus-5-5, effort high. Actual model will be recorded from the completed response metadata.
- Feature Dev loaded by explicit session directory. Its full workflow assumes an existing codebase; initial task uses its architect capability directly.
- CockroachDB: no plugin found by Codex's plugin-management search and no Claude MCP servers configured. No database or cloud account provisioned. More plugins may exist in the plugin directory: https://chatgpt.com/plugins.
- GitHub: supervisor created pg1590/cibc-collections-copilot and made it public to enable access. Connector now reports push/admin permission. Confidential source extracts, raw Claude outputs and credentials stay local. Public visibility remains the supervisor's change.

## Earlier connector write verification
A README bootstrap write returned HTTP 403 (Resource not accessible by integration), despite reported push/admin metadata. Existing SSH authentication was also rejected by GitHub (publickey). The remote is still empty; local repo and reviewed artifact are saved.

Resume verification on 2 October 2026: the README create retry again returned 403, and the repository contents endpoint confirmed that the repository is empty. The connector lists installations for two other accounts, but none for pg1590. A missing pg1590 repository-app installation is the likely cause; this is an inference from the installation listing, not proof of the complete authorization configuration. Enable the connected GitHub App on pg1590 with access to cibc-collections-copilot and repository contents write permission, then retry the reviewed-files upload. No GitHub CLI is installed locally.

## Verified SSH delivery

After the supervisor added the public authentication key on 2 October 2026, GitHub SSH returned `Hi pg1590! You've successfully authenticated`. The SSH test exits with code 1 because GitHub does not provide shell access; the response confirms authentication. `git ls-remote origin` succeeded with no refs, then `git push -u origin main` successfully created remote main and configured tracking. Reviewed project files and local commit history are uploaded; source PDFs, extracts, credentials, raw responses and generated delivery artifacts remain local. SSH resolves project delivery without requiring connector write access.
