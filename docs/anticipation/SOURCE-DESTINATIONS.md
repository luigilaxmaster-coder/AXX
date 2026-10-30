# Observed-context destination consent

This contract is implemented behind closed activation gates.
`SOURCE_PLANNING_READY=False` and effective source-provider availability remain
closed. No migration enables observation, retention, sensitive processing, or
provider transmission. Tests use synthetic data and isolated loopback HTTP.

## Independent permissions and public metadata

`observation_targets[].allowed_profile_ids` is a sorted list of up to 16 unique
lowercase 32-hex identifiers. Omission and `[]` grant no recipient permission.
Only window and clipboard sources support this field. Sending also requires
their existing observe/retain/send permissions, fresh references, context scope,
and activation gate. Microphone, unverified application scope, SDK/Codex,
gateways, proxy and unknown routes remain outside this increment.

The existing `GET /axx-api/providers` adds `profile_id`,
`source_context_eligible`, `source_context_reason`, and `allow_sensitive` to each
configured row. Eligibility is configuration metadata, not consent to observe or
send. Closed reason codes are `eligible`, `disabled`, `candidate_only`,
`gateway_not_supported`, `unsupported_transport`, and `sensitive_not_allowed`.
Eligible recipients require enabled direct HTTP(S), an implemented OpenAI or
Anthropic protocol, and explicit `allow_sensitive=True`.

Canonical `profile_id()` binds name, base URL, model, protocol and route kind.
Changing that identity does not inherit the prior sensitive-processing consent.
`POST /axx-api/providers/save` accepts an explicit strict boolean
`allow_sensitive`; omission preserves consent only for the same identity.
Selecting a source recipient never changes that connection permission.
Unavailable previously saved IDs can be retained or removed, but cannot become
authority for another profile. New IDs must exist and be eligible.

## Causal admission and publication

References remain exactly `target_id`, `consent_digest`, `observation_id`, and
`generation`; the target digest includes its destination list. ActionLearning
retains all causal references across repair, up to the existing four-reference
bound. Before reserving a mission model call it takes the intersection of all
their allowed recipients, current eligibility and explicit manual selection.
An empty intersection abstains before reservation or egress.

`InferenceAdapter.route(..., source_policy=SourceDestinationPolicy(...))` is an
internal keyword argument, separate from the model/request envelope. The object
seals the initial recipient set; later permission additions cannot widen that
request. The host revalidation closure retains exact causal references and
selection. New publication is also rejected if the admitted destination set no
longer remains eligible. Existing consent/publication guards continue to discard
late response text, steps and automatic skill creation after invalidation.

## Existing worker pipes: per-attempt permission

Legacy requests retain their single terminal JSON protocol. Internal source
requests use the `AXX-SOURCE-1` preamble and their bounded request on the same
stdin/stdout pipes. Before each eligible attempt, the Router requests host
admission using a frame containing version, strictly increasing ordinal, exact
profile ID and a fresh nonce. Frames are at most 512 bytes, with at most 16
admission requests and one outstanding request. Duplicate JSON keys, replay,
unexpected fields/types, denial, EOF or deadline do not authorize dispatch.
Only the exact response with strict `permitted: true` permits that attempt.
The existing writer handles both the initial payload and acknowledgements through
a bounded queue; the host deadline/cancellation loop never waits on a pipe write.

The host checks the original worker configuration, current configuration,
sealed recipient set, causal consent, cancellation and deadline. Policy-lock
acquisition uses cancelable waits of at most 20 ms. It does not hold the adapter
lock while waiting and does not spawn an authority thread. It rechecks the
configuration snapshot, cancellation and deadline before granting permission.
The Router recalculates the remaining deadline before quota reservation.
Selection, fallback, cost filters and attempt accounting remain in the Router.

This permission is the admission point of one attempt, before its quota and
HTTP call. A subsequent cancellation cannot undo a request already admitted or
sent. Configuration changes cancel active source requests; source changes revoke
their existing leases. Denial of a later attempt does not erase earlier consumed
attempts. Unknown crash/cancel outcomes remain conservative; there is no new
retry or special refund mechanism.

Admission frames are not delivery acknowledgements. The existing
`mission_model_calls.source_dispatch_json` ledger retains its independent
not-sent/unknown/runtime-delivered/endpoint-confirmed evidence. Only actual HTTP
response headers confirm the configured endpoint; neither an admission permit,
attempt count nor terminal model text proves downstream processing. Gates stay
closed pending a separate activation review.
