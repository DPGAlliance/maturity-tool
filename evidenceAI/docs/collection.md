# Source Collection

The MAT pilot investigates only Source Code Accessibility, Governance, and
Flexible Architecture. It shares the supplied links, collected excerpts,
published links, GitHub file inventory, unresolved section gaps, and prior
actions with the model. Source content is untrusted data, never instructions.

The model can return one JSON action at a time: read an existing supplied or
already-collected link, list files in an already-known public GitHub repository,
read a file from that inventory, search Brave for a currently unresolved section
gap, or finish. The service validates every action and rejects arbitrary URLs,
repositories, files, and resolved-gap searches.

Collection is capped at 12 actions, 8 page reads, 2 repository listings, 8
GitHub file reads, 2 Brave searches, and 40 files per listing. Web reads allow
only public `http` or `https` URLs on standard ports, reject private or
non-resolving targets, do not follow redirects, and cap responses at 1 MB.
Readable excerpts are limited to 4,000 characters. Every requested action and
its execution outcome are persisted in the authenticated job trace. Brave
results remain discovery metadata and are not subsequently fetched unless a
later model action selects an allow-listed result.
