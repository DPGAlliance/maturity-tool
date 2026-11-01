Yes. The first EvidenceAI workflow should be **MAT-only asynchronous evidence collection/autofill**, with no verification or scoring changes yet.

Nomination context is optional enrichment, not a dependency:

- A registered product can arrive with prior nomination resources and facts.
- A non-registered product can arrive with only a name, website, or GitHub owner/repository.
- The same collection chain runs in both cases.
- More context produces better suggestions; missing/failed sources produce partial results, not a failed overall job.

## Scope

**In scope**
- Discover useful public resources for all MAT evidence sections.
- Suggest evidence links and, only where the source directly supports it, suggested checkbox selections.
- Return structured suggestions per MAT page/indicator.
- Include confidence, explanation, source URLs, excerpts/path references, and collection status.
- Support repository URLs and GitHub organization/owner URLs.
- Persist jobs, discovered resources, facts, and suggestions in EvidenceAI’s own database.
- Use realistic project inputs as a fake MAT-backend request during development.

**Out of scope today**
- Evidence verification/relevance decisions.
- Reviewer workflows.
- Private evidence.
- Writing accepted values into MAT.
- MAT scoring or confidence-score changes.
- Direct nomination-system integration.

## Proposed Interface

### Start collection

`POST /v1/mat/autofill-jobs`

```json
{
  "assessment_id": "opaque-mat-reference",
  "product": {
    "id": "optional-nomination-or-mat-product-reference",
    "name": "Example Product",
    "version": "optional"
  },
  "context": {
    "organization_name": "optional",
    "description": "optional product description",
    "website_url": "https://example.org",
    "documentation_urls": ["https://docs.example.org"],
    "github_url": "https://github.com/example-org/example-repo",
    "provided_resources": [
      {
        "url": "https://example.org/governance",
        "source": "nomination_context"
      }
    ]
  },
  "requested_indicators": ["all"]
}
```

`github_url` accepts either a repository or a GitHub owner/organization page. `provided_resources` is deliberately generic, so future nomination context can be passed through without changing the contract.

The response is immediate:

```json
{
  "job_id": "uuid",
  "assessment_id": "opaque-mat-reference",
  "status": "pending",
  "status_url": "/v1/mat/autofill-jobs/uuid"
}
```

### Poll results

`GET /v1/mat/autofill-jobs/{job_id}`

A completed result returns an EvidenceAI-generated product ID, the opaque MAT assessment reference, the MAT form-schema version, and suggestions grouped by MAT page:

```json
{
  "job_id": "uuid",
  "project_id": "evidenceai-project-uuid",
  "assessment_id": "opaque-mat-reference",
  "status": "completed",
  "mat_schema_version": "agreed-version",
  "pages": [
    {
      "indicator_id": "source_code",
      "status": "partial",
      "suggestions": [
        {
          "target_type": "evidence_link",
          "target_id": "ev_src_repo_link",
          "value": "https://github.com/example-org/example-repo",
          "status": "ai_suggested",
          "confidence": 0.98,
          "reason": "Provided public GitHub repository for the named product.",
          "sources": [
            {
              "url": "https://github.com/example-org/example-repo",
              "source_type": "provided_github_url"
            }
          ]
        },
        {
          "target_type": "capability_checkbox",
          "target_id": "src_public_repo",
          "value": true,
          "status": "ai_suggested",
          "confidence": 0.98,
          "reason": "The supplied repository is publicly accessible.",
          "sources": [
            {
              "url": "https://github.com/example-org/example-repo",
              "source_type": "github_repository"
            }
          ]
        }
      ]
    }
  ]
}
```

MAT owns its saved answers. EvidenceAI returns suggestions only. MAT can render every suggestion in a distinct suggestion state, then let the owner accept, edit, replace, or reject it.

## Collection Chain

1. **Create and persist job**
   - Store the opaque MAT assessment reference and all supplied context.
   - Generate EvidenceAI `project_id` and `job_id`.
   - Deduplicate equivalent active requests safely.

2. **Normalize sources**
   - Canonicalize website, docs, resource links, and GitHub URLs.
   - Identify whether the GitHub URL is a repository or owner page.
   - Treat nomination resources as supplied context, not as verified facts.

3. **Collect directly available information**
   - GitHub repository: metadata, README, LICENSE, CONTRIBUTING, SECURITY, GOVERNANCE, releases, issue/discussion links, CI workflow names, API/architecture links.
   - GitHub owner page: bounded repository discovery and ranking against product name/context.
   - Website/docs: bounded fetch of supplied pages and direct relevant links.
   - Existing supplied evidence URLs: retain them as high-priority candidates.

4. **Discover missing resource candidates**
   - Governance/decision documents.
   - Security policy and CI/security documentation.
   - API references, OpenAPI/schema pages, standards documentation.
   - Roadmaps, release plans, issue trackers, discussion forums.
   - Architecture, extension/plugin, deployment, privacy, compliance, and cost pages.

5. **Extract and suggest**
   - Create structured resource records and extracted facts.
   - Use the LLM to map collected material to MAT indicator fields and explain why.
   - Suggest evidence links for all applicable sections.
   - Suggest checkboxes only where direct evidence supports a cautious claim.
   - Leave unsupported boxes unselected and return `no_suggestion` or `insufficient_context`.

6. **Return partial results**
   - A failed website fetch must not discard useful GitHub results.
   - A missing repository must not prevent website/docs discovery.
   - Per-page and per-source errors appear in the job result without exposing internal details.

## MAT Coverage Target

The collector should search for candidate evidence across all MAT pages:

| MAT page | Main resources to seek | Checkbox suggestions |
| --- | --- | --- |
| Governance | governance docs, maintainers, decision logs, meeting notes | Cautious |
| Secure Development | `SECURITY.md`, secure-development docs, CI workflows, scan artifacts | Cautious |
| Regulatory Compliance | compliance/privacy documentation, regulatory guidance | Usually link-only |
| Security Controls | security guidance, architecture, audit/attestation references | Mostly link-only |
| Open Standards | API docs, schemas, OpenAPI, standards references, export docs | Direct only where explicit |
| Product Roadmap | roadmap, release plan, issue tracker, discussions | Cautious |
| Source Code Accessibility | public repo, license, developer/contribution docs | Strongest checkbox candidates |
| Total Cost of Ownership | deployment requirements, pricing, cost documentation/calculators | Usually link-only |
| Flexible Architecture | architecture docs, modules, plugins, extension examples | Cautious |

## Persistence and Worker Plan

EvidenceAI should have its own:

- `autofill_jobs`
- `projects`
- `input_sources`
- `resources`
- `extracted_facts`
- `mat_suggestions`

A separate worker service claims queued jobs, performs collection/LLM work, records progress and heartbeats, and completes or partially completes the job. The API remains responsive and serves job status/results.

The field-to-evidence mapping must be a versioned, readable registry. MAT’s current client-side IDs are recoverable, but they are not yet a guaranteed integration contract. EvidenceAI should return IDs such as `source_code`, `ev_src_repo_link`, and `src_public_repo` only after MAT backend developers agree on a versioned schema.

## Implementation Order

1. Define the MAT suggestion-result contract and field-mapping registry.
2. Add job persistence, polling, worker lifecycle, and fake MAT request fixtures.
3. Collect supplied GitHub repository/owner, website, docs, and nomination resources.
4. Persist resources/facts with provenance.
5. Add LLM page-by-page suggestion generation for all MAT evidence sections.
6. Build a real-project end-to-end fixture and inspect result quality.
7. Add verification as a separate later workflow, reusing but not overwriting autofill resources and suggestions.

## Decisions Needed Before Implementation

1. **Project correlation:** Will MAT send an opaque `assessment_id`, a stable product ID, or both? EvidenceAI can support both, but MAT must define the correlation key.
2. **Public-web discovery:** Beyond supplied URLs, should EvidenceAI use a web-search provider to discover governance/security/API/etc. pages? If yes, which provider/API is approved?
3. **GitHub scope:** Is public GitHub.com-only sufficient initially, with GitLab, GitHub Enterprise, and private repositories explicitly deferred?
4. **Test product:** Which real public product should be the primary development fixture? It should have a public repo, website, docs, and enough material across several MAT sections.
