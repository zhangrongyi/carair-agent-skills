# Administrator setup and rotation

1. Deploy and separately authorize the company management system's development schema, persistent private image directory, and `development.enabled` setting. Complete and reconcile the one-time Lark migration before switching employees. The private directory must be outside `server/public` and included in protected backups.
2. Grant the `development/*` menu permissions to the appropriate employee roles. Keep `development/reviewStage` separate from creation/transition permissions; the server rejects self-review. Only root administrators can issue, list, and revoke Codex draft tokens.
3. For each employee, issue a separate scoped draft token in the development page. Show it once; the employee stores it with `workflow.py configure-credential` on their machine. Rotate by issuing a replacement and revoking the prior token. Do not distribute tokens through chat.
4. Keep `query-carair-products` read-only token separate. Its scope and access are unchanged.
5. Verify product `health` and research `inspect` without writing. Run `apply` only for an authorized real research item after the module and migration have passed acceptance.

The company project is the source of truth after cutover. Lark is retained as read-only history; normal Skill execution makes no Lark API calls.
