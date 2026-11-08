# AI Draft Generation

After the bounded three-section investigation, the worker calls the OpenAI
Responses API with model `gpt-6-luna` only when `secrets/openai_api_key` is
available. It asks for JSON drafts constrained to the collected URLs and the
Source Code Accessibility, Governance, and Flexible Architecture registry
fields. Suggestions without a valid collected citation are discarded.

Every returned item remains `origin: ai` and `state: suggested`. It is a draft
for MAT owners or reviewers to evaluate, never an accepted answer or a MAT
writeback. The first experiment uses requested indicator IDs verbatim until the
MAT backend publishes its formal field registry.

Evidence-field drafts and capability drafts are returned in separate arrays.
EvidenceAI does not assume a MAT frontend acceptance flow for either array and
never writes any draft back to MAT.

When MAT requests `"all"`, EvidenceAI requests one `evidence_summary` draft
when at least one cited source is available. This provides a useful playground
result before real MAT indicator IDs are registered.

Each job also stores an internal generation trace containing the model output,
outcome, and rejection reason. Use the authenticated job trace endpoint to
review discarded responses when tuning prompts.
