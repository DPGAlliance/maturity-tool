# Source Collection

The worker fetches only MAT-supplied public `http` or `https` URLs. It allows
only standard web ports, rejects private or non-resolving network targets, does
not follow redirects, and caps each response at 1 MB. It stores a normalized
4,000-character excerpt and source metadata for each successful fetch.

Brave results are stored as bounded discovery metadata only. EvidenceAI does
not fetch those candidates yet, so search does not expand the network access
surface beyond URLs explicitly supplied by MAT.
