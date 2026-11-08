# Source Collection

The worker fetches only MAT-supplied public `http` or `https` URLs. It allows
only standard web ports, rejects private or non-resolving network targets, does
not follow redirects, and caps each response at 1 MB. It stores a normalized
4,000-character readable-text excerpt, outgoing-link list, and source metadata
for each successful fetch. Scripts, styles, and page chrome are excluded from
HTML excerpts.

Brave results are stored as bounded discovery metadata only. EvidenceAI does
not fetch those candidates yet, so search does not expand the network access
surface beyond URLs explicitly supplied by MAT. A later bounded investigation
step may follow persisted links when they satisfy registry-defined evidence gaps.

The current bounded follow-up step checks up to eight linked pages whose paths
indicate likely MAT evidence, including governance, security, architecture,
contribution, license, roadmap, API, standards, or workflow material. These
follow-ups remain subject to the same public-network and response-size limits.
Follow-up requests use a five-second timeout. Each successful fetch is persisted
immediately and the job reports `collecting_sources` progress while collection
continues.
