# Search Discovery

EvidenceAI uses Brave Search as the initial public-source discovery provider.
The worker receives the token from the local Docker secret
`secrets/brave_search_api_key`; it must not be committed or exposed to MAT
browsers.

The provider returns at most five candidates for each product query. Results are
only discovery metadata at this stage: EvidenceAI does not fetch candidate URLs,
generate suggestions, or write to MAT yet. Other discovery providers can be
added behind the same result shape without changing the MAT API.
