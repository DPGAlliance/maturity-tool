# AI Draft Generation

The worker calls the OpenAI Responses API with model `gpt-6-luna` only when
`secrets/openai_api_key` is available. It asks for JSON drafts constrained to
the URLs collected for the job. Suggestions without a valid collected citation
are discarded.

Every returned item remains `origin: ai` and `state: suggested`. It is a draft
for MAT owners or reviewers to evaluate, never an accepted answer or a MAT
writeback. The first experiment uses requested indicator IDs verbatim until the
MAT backend publishes its formal field registry.

Each job also stores an internal generation trace containing the model output,
outcome, and rejection reason. Use the authenticated job trace endpoint to
review discarded responses when tuning prompts.
