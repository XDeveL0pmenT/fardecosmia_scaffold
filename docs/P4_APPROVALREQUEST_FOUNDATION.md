# P4 APPROVALREQUEST FOUNDATION REPORT

## 1. Changed files

P4 added or changed:

- `world/models.py`;
- `world/migrations/0019_approvalrequest.py`;
- `world/services/approvals.py`;
- `world/services/audit.py`;
- `world/views.py`, `world/urls.py`, `world/admin.py`;
- `world/templatetags/audit_json.py`;
- `world/templates/world/approval_list.html`;
- `world/templates/world/approval_detail.html`;
- `world/templates/world/_technical_details_summary.html`;
- `world/templates/world/audit_detail.html`;
- `campaigns/views.py`;
- `campaigns/templates/campaigns/gm_dashboard.html`;
- `campaigns/templates/campaigns/campaign_list.html`;
- `templates/campaigns/_campaign_quickbar.html`;
- `templates/base.html` and `static/css/app.css`;
- `world/tests/test_approvals_p4.py`;
- `scripts/benchmark_approvals_p4.py`;
- `AGENTS.md`, `WORLD_HANDOFF_v2.md`, architecture guardrails and Master Roadmap;
- this report.

No C4/R1/M1 solver or atlas implementation was changed for P4.

## 2. Migration

`world.0019_approvalrequest` creates the ApprovalRequest table, foreign keys and
query indexes. It is additive and does not delete or rewrite existing data. The
migration was applied successfully to the current local development database.

## 3. ApprovalRequest model

The campaign-scoped model stores type, lifecycle status, requester and resolver,
real and world-time snapshots, a generic optional target and its label snapshot,
versioned JSON payload, dedupe/expiry fields, bounded structured result and one
operation UUID. Default ordering is newest first.

## 4. Campaign scope

`campaign` is required and uses `CASCADE`; all service lookups include both
campaign and request ID. UI access begins with P2 campaign access helpers. A
handler remains responsible for validating that any domain target is valid for
the same campaign; the proof handler and regression test demonstrate this.

## 5. Status lifecycle

Statuses and Russian labels are:

- `PENDING` — «Ожидает решения»;
- `APPROVED` — «Одобрено»;
- `REJECTED` — «Отклонено»;
- `CANCELLED` — «Отменено»;
- `EXPIRED` — «Истекло».

A new row must start pending. Services allow only pending-to-terminal transitions.

## 6. APPROVED semantics

The handler's domain `apply()` runs before the request is marked approved. If
revalidation, apply, result validation, request save or audit fails, the atomic
block rolls back and the request does not become approved.

## 7. Requester/resolver snapshots

Nullable `SET_NULL` user foreign keys are paired with
`requester_label_snapshot` and `resolved_by_label_snapshot`. Human history
therefore remains readable after a user is deleted.

## 8. World-time snapshots

`requested_world_minutes` and `resolved_world_minutes` copy
`Campaign.world_minutes` at their respective lifecycle moments. Real-world
timestamps are separately stored in `requested_at` and `resolved_at`.

## 9. Target snapshot

The optional generic target uses ContentType/object ID for lookup and a durable
`target_label` for display. Deleting the target makes the live relation `None`
without erasing the human label. Handlers decide whether a missing target makes
the pending intent stale.

## 10. operation_id

One UUID is assigned at creation and is immutable. Creation, domain mutation and
resolution AuditLog rows reuse it, allowing one human operation to be correlated
without copying raw payload data into audit history.

## 11. Payload version/size/security

Payload and result must be JSON objects. Both are passed through the shared P3
secret-key validator and have a 64 KiB encoded limit. Oversized values fail
explicitly. `payload_version` must match the registered handler version.

## 12. Handler registry

`world.services.approvals` exposes a process-local whitelist registry through
`register_approval_handler()`, `unregister_approval_handler()` and
`get_approval_handler()`. Names must be namespaced identifiers. P4 deliberately
registers no fictional purchase or travel handler.

## 13. Handler contract

Every handler supplies `validator`, `presenter` and `apply`. It may override
`can_request`, `can_approve`, `can_cancel`, `revalidate`, payload version and the
requirement for a resolution note. Default permissions use P2 campaign access.

## 14. Human presenter contract

The presenter returns `ApprovalPresentation`: human type label, title, summary,
label/value details, explicit consequences, optional target/applicability/result
messages. Titles, summaries and list sizes are bounded and consequences are
mandatory. Templates do not interpret raw payload into business meaning.

## 15. Request-time validation

`create_approval_request()` resolves the registered handler, validates and
normalizes payload, checks expiry/target/dedupe shape and permissions, invokes
handler revalidation, builds the human presentation, then stores the row and its
creation audit atomically.

## 16. Approval-time revalidation

`approve_request()` locks and reloads the request, checks status/expiry and actor
permission, then invokes the handler's `revalidate()` immediately before apply.

## 17. Stale/conflict behavior

Handlers raise a human-readable `ApprovalConflict`. Stale expected state,
deleted required targets and cross-campaign targets are covered. No domain write,
approved status or success audit survives a failed transaction.

## 18. dedupe

An optional `dedupe_key` prevents another unexpired pending request with the same
campaign, request type and key. This is service-level validation, as permitted by
P4, and the key is absent from normal UI.

## 19. Expiry

`expires_at` is optional and timezone-aware. GET pages calculate an effective
expired status without mutating data. An explicit decision or
`expire_request()` locks the row and persists `EXPIRED` plus an AuditLog row.

## 20. Cancel/reject

Authorized campaign decision-makers may reject; the handler's cancellation rule
normally lets the requester cancel their own pending request. Both transitions
store resolver snapshots, world time, optional note and lifecycle audit.

## 21. Result storage

Only an approved request may contain non-empty `result`. The handler returns the
small structured JSON result after successful apply; it receives the same 64 KiB
and secret-key validation as payload.

## 22. Terminal immutability

Model save prevents changing terminal rows and prevents rewriting immutable
intent fields after creation. Instance deletion is rejected. Normal views and
admin provide no mutation route around lifecycle services.

## 23. Transactions

Create, approve, reject, cancel and expire operations run inside
`transaction.atomic()`. Approval includes domain apply, structured result,
request resolution, domain audit and lifecycle audit in that transaction.

## 24. select_for_update / concurrency

Every resolution path fetches the campaign-scoped request with
`select_for_update()`. PostgreSQL therefore serializes competing decisions on
the same request. SQLite is retained only for local bootstrap and cannot prove
row-level locking.

## 25. Double-approval proof

The sequential regression proves a second approval raises
`ApprovalAlreadyResolved` and produces exactly one domain apply audit and one
approval audit. A real two-thread TransactionTestCase provides the same proof on
databases supporting row locks and is conditionally skipped on SQLite.

## 26. P2 access integration

The workflow uses `can_view_campaign()` and `can_manage_campaign()` from the P2
access layer. Role remains CampaignMembership-scoped; no role flag was added to
User.

## 27. Final permission matrix

| Actor | GM queue | Own request detail | Other request detail | Approve/reject | Cancel own pending |
|---|---:|---:|---:|---:|---:|
| Campaign GM | yes | yes | yes | yes | handler-specific |
| Campaign player/requester | no | yes | no | no | yes by default |
| GM of another campaign | no | no | no | no | no |
| Global Canon Editor only | no | no | no | no | no |
| Outsider | no | no | no | no | no |
| Superuser | yes | yes | yes | yes | handler-specific |

## 28. GM queue

`campaign_approval_queue` defaults to pending, non-expired requests and supports
human-labelled status, type, requester and date filters. Pagination is 30 rows.
The GM dashboard displays up to five current pending requests.

## 29. My Requests

`my_approval_requests` shows only the signed-in user's requests in the selected
campaign, with the same safe human filters and pagination. It is linked from
campaign navigation for both player and GM memberships.

## 30. Request detail

The shared detail view applies GM-or-owner scoping, shows requester, target,
request/world time, intent, consequences, applicability, resolution and related
approval lifecycle history. Unauthorized access returns project-consistent
403/404 responses.

## 31. Human status labels

Normal pages use Django choice labels and an effective expiry label. Internal
status tokens are not rendered as primary UI.

## 32. Human request presentation

The first screen answers who requested what, when, for which target and why.
Stored title/summary keep historical pages readable if a handler is later absent.

## 33. Consequences presentation

Every presenter must supply at least one explicit consequence. The detail page
places the «Что произойдёт после одобрения» panel before controls and technical
data.

## 34. Collapsed technical data

Raw payload, result, version, IDs and operation UUID are placed inside the shared
collapsed `_technical_details_summary.html` component. JSON is escaped. The P3
audit detail now reuses the same presentation-only component.

## 35. Empty/mobile states

Queue and My Requests have explanatory empty states. P4 CSS includes compact
cards, filter wrapping, horizontally scrollable campaign navigation and narrow
action layouts; the reviewed 375 px viewport had matching client and scroll
widths with no page-level horizontal overflow.

## 36. P3 AuditLog integration

Actions are `approval_request.created`, `.approved`, `.rejected`, `.cancelled`
and `.expired`. They use the shared safe serializer, campaign scope, snapshots
and operation UUID. Domain handlers may add their own audit rows to the group.

## 37. Audit summary readability

Lifecycle summaries name the human request and decision. P3 template mappings
provide Russian action names/descriptions/tones. Raw approval payload is omitted
from compact audit serialization.

## 38. operation_id propagation

The handler receives `operation_id` as an apply argument. Tests prove creation,
domain and resolution rows all retain the ApprovalRequest UUID.

## 39. Admin behavior

ApprovalRequest is visible to superusers as read-only diagnostics. Add, change
and delete permissions are disabled, and payload/result/UUID fields are
read-only.

## 40. IDOR/security tests

Tests cover campaign GM, foreign GM, requester, another player, Global Canon
Editor-only user, outsider and superuser. Foreign campaign/request ID access does
not expose another request. GET of an expired request creates no mutation/audit.

## 41. Secret/payload tests

Tests reject unknown fields, secret-like keys, oversized payload and oversized or
secret-bearing result. HTML/script text is escaped on the technical view.

## 42. Registry tests

Tests cover unknown types, mandatory presenter, payload-version mismatch,
historical requests whose handler disappeared, human presentation constraints,
dedupe and handler-required decision notes.

## 43. UI readability tests

Tests assert human status/type, intent and consequence headings, authorized-only
controls, collapsed technical details, escaped JSON, resolved result/resolver,
readable empty state and absence of raw `PENDING` in normal content.

## 44. Browser/manual verification

An isolated temporary database and local server were used. The GM pending queue,
detail, approve/reject controls, approved result/history and mobile layout were
reviewed. The requester My Requests page, own detail, cancellation control and
absence of GM controls were reviewed. Temporary settings, database and server
were removed/stopped afterward. Reject/cancel transitions are also exercised by
request-level automated tests.

## 45. 5-second readability acceptance

Passed: the type/title, requester and requested effect are visible before any
technical fields, while consequences occupy a distinct panel. UUID and raw JSON
require intentionally opening «Технические данные».

## 46. Query counts

Rollback-only benchmark results on the current development environment:

- GM queue: 6 queries;
- request detail: 5 queries.

No per-row query is made by the templates.

## 47. Performance

Twenty rollback-only repetitions produced:

- create median: 1.873 ms;
- approval framework median: 3.863 ms;
- queue response: 8,891 bytes;
- detail response: 10,859 bytes.

These figures measure framework/database workflow with a trivial proof handler,
not the future cost of a domain action.

## 48. Tests added

`world/tests/test_approvals_p4.py` contains 24 tests covering model/registry,
lifecycle/rollback, permissions/IDOR, audit grouping, UI readability and
concurrency. `scripts/benchmark_approvals_p4.py` is a non-unit benchmark and
rolls back all temporary rows.

## 49. Full test result

`python manage.py test --verbosity 1`:

```text
Ran 294 tests in 271.277s
OK (skipped=1)
```

The skip is the PostgreSQL-only concurrent row-lock proof on local SQLite.

## 50. manage.py check

Passed: `System check identified no issues (0 silenced).`

## 51. makemigrations --check --dry-run

Passed: `No changes detected`.

## 52. M1 regression

No M1 atlas/map code was changed for P4. Its tests are included in the passing
full suite.

## 53. R1 regression

No Region weather lifecycle or environment summary behavior was changed for P4.
R1 tests are included in the passing full suite.

## 54. Atmosphere scope confirmation

Atmospheric solvers, coefficients, snapshot lifecycle and climate physics were
not changed. Generated weather/snapshot rows do not create approval audit spam.

## 55. WORLD_HANDOFF update

`WORLD_HANDOFF_v2.md` now records P4 as implemented and states its atomic,
human-first, registered-intent invariants while leaving gameplay handlers future.

## 56. AGENTS update

`AGENTS.md` now requires registered handlers, versioned/validated payloads, human
presenters, approval-time revalidation, atomic apply/audit and resolved-request
immutability.

## 57. Guardrails update

The architecture guardrails now state that ApprovalRequest is neither WorldEvent
nor an arbitrary command queue and that future domains must extend this one
foundation.

## 58. Master Roadmap status

Only the P4 foundation capabilities are marked complete. Purchases, travel,
rewards, multi-party approval and P5 remain unchecked.

## 59. Known limitations

- P4 contains a test/proof handler only; no production gameplay type is
  registered because its canon/domain rules do not yet exist.
- Multi-party/quorum decisions are not represented.
- Automatic scheduled expiry processing is not present; effective expiry is
  displayed without GET mutation and can be persisted by an explicit service.
- Row-lock concurrency must be executed against production-like PostgreSQL;
  SQLite skips that one test.
- The handler registry is in-process and future production handlers must register
  deterministically during application startup.
- Lifecycle invariants are enforced by model/service boundaries; deliberate raw
  SQL or `QuerySet.update()` is outside the supported application API.

## 60. Future Inventory/Purchase path

A future purchase domain can register a versioned handler containing stable
character/shop/item/quantity references and expected price/version. Its
revalidation would confirm current stock, price and authority; its atomic apply
would write ledger/inventory rows and grouped audits. None of those models or
rules were implemented in P4.

## 61. Future Travel path

A future Travel handler can present route, participants, cost and consequences,
then revalidate current positions/world state and call the dedicated Travel
service. P4 does not define routes, movement physics or travel canon.

## 62. Future multi-party extension

Multi-party consent will require an explicit participant/decision/quorum layer
linked to one ApprovalRequest while preserving the final atomic apply rule. P4
does not infer quorum or consent rules.

## 63. Future P5 path

WorldEvent remains a separate event/effect timeline. A future approved domain
action may create or schedule a WorldEvent through that domain service, but an
ApprovalRequest itself does not become an event. P5 was not started.

## 64. Confirmation of stopped scope

P5, CharacterKnowledge, M2, Inventory/Purchases, Travel and C5 were not started.
P4 stops at the reusable approval foundation, documentation, verification and
this report.
