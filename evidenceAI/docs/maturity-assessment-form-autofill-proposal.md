# Maturity Assessment Form: AI Autofill and Evidence Validation Proposal

## Summary

The Maturity Assessment Tool (MAT) can substantially reduce blank-page work by
collecting public evidence from a product's repository, documentation and public
website. It can also give product owners and reviewers useful first-pass evidence
checks. It must not present either capability as an independent certification of
the product.

The appropriate workflow is two rounds:

1. **Pre-population:** collect public facts and suggest editable capabilities and
   evidence links before the product owner completes the assessment.
2. **Evidence validation:** after the owner supplies or confirms evidence, check
   that links resolve, extract their content, and assess their relevance to the
   specific MAT indicator.

The result should distinguish three separate facts that the current form conflates:

- an evidence field is completed;
- the linked resource is reachable and relevant to the stated indicator;
- the underlying claim is credible enough for a reviewer to accept.

Only the first is currently observable from the public client implementation.
The second and third are a good targets for automation.
 But the final decision remains a product-owner and
reviewer decision, especially for internal controls, audits, compliance and costs.

This report evaluates the public workflow at
`https://maturity.digitalpublicgoods.net/assessments/new` as observed on 2026-10-10.
It covers its ten input steps and its summary step. The public page states that a
DPG product owner must log in through the nomination portal to submit; this report
does not assume access to authenticated or backend-only behavior.

## Product Principles

### Assistance, not automatic assessment

Suggested values must be visibly labelled **AI-suggested**, remain editable, and
carry evidence links and a short explanation. The tool should leave a field blank
when evidence is insufficient rather than selecting a flattering capability.

### Validate evidence against the field, not in the abstract

For example, an accessible GitHub repository is relevant evidence for Source Code
Accessibility, but not proof of a security audit. A valid-looking PDF is not proof
that its audit scope, date and findings satisfy the Security Controls indicator.

### Treat private evidence honestly

Some evidence, particularly audit reports and compliance documents, cannot safely
be made public. A per-evidence-item `private / declared but not publicly
verifiable` option should preserve the claim without incorrectly marking it
AI-verified or treating the field as empty.

### Preserve source provenance

Every suggestion and validation result should record:

- source URL or repository path;
- retrieval time and content hash where practical;
- extractor used, including GitHub API, crawl or deps.dev;
- exact supporting excerpt or structured fact;
- indicator and evidence field it supports;
- suggestion/validation status and reason.

This makes the output reviewable and permits later re-validation when a document
changes or a link expires.

## What "Validation" Can Reliably Mean

| Level | Automated result | What it does not establish |
| --- | --- | --- |
| Technical | URL resolves, file downloads, content can be extracted, page is not obviously stale | Truth of the product-owner claim |
| Relevance | The content contains material relevant to the requested evidence field, with cited excerpts | Completeness, implementation, scope or independence |
| Consistency | Submitted capability is consistent with discovered public evidence and prerequisites | That undocumented controls do not exist |
| Human review | Reviewer accepts, rejects or requests clarification | This must remain a human decision for high-impact claims |

An LLM relevance result should be one of `valid`, `likely_valid`, `questionable`,
`invalid`, or `unverifiable`, accompanied by a short reason and evidence excerpt.
`unverifiable` is important: a private audit report is neither invalid nor publicly
verified.

## Proposed Backend Contract

The existing website should remain the user interface. A shared backend can expose
small assessment-scoped operations rather than a separate application UI.

### Pre-population

`POST /evidence-collection/jobs`

Input:

- `repository_url`
- `website_url` and optional `documentation_url`
- product/organization name, if known
- requested form (`maturity_assessment`)
- selected sections or all sections

Output/job result per field:

- `suggested_value` or no suggestion
- `status`: `filled`, `partial`, `needs_user_input`, `not_applicable_candidate`
- `confidence`: collection confidence, not maturity confidence
- source/evidence records and explanation
- capability prerequisites that the user should confirm

### Validation

`POST /evidence-validation/jobs`

Input:

- assessment ID or submitted indicator/evidence values
- evidence URL, uploaded-document reference, or `private_evidence` declaration
- indicator ID and evidence-field ID

Output per evidence item:

- reachability and retrieval timestamp
- extracted title/type/date where available
- `valid`, `likely_valid`, `questionable`, `invalid`, or `unverifiable`
- reason, cited excerpt and freshness warning
- human-review recommendation

The backend should cache public retrievals for a short, explicit retention period
(for example 30 days), respect robots/rate limits, and never make a private upload
available outside its authorized review path.

## Sources Worth Collecting

| Source | Strong uses | Limits |
| --- | --- | --- |
| GitHub/repository API | repository identity, license, releases, contribution files, issue templates, workflows, security policy, public roadmap links | Presence of a file is not proof that a process is used |
| Repository contents | README, `LICENSE`, `CONTRIBUTING`, `SECURITY.md`, `CODE_OF_CONDUCT`, CI configuration, architecture and API docs | Private repos and external operations are invisible |
| Public documentation/site crawl | governance, roadmap, architecture, API/export, deployment, privacy/compliance and cost documents | Crawl scope must be bounded and citations retained |
| deps.dev | package/dependency metadata and disclosed vulnerability/advisory signals when a supported package can be identified | It does not prove secure development practice, audit status or product-level security posture |
| Submitted URLs/documents | direct evidence for the exact field | Must be checked for accessibility, relevance, date and scope |

## Step-by-Step Feasibility

### 1. Assessment Details

**Form inputs:** product name, optional version, visibility, assessor name/email,
assessor role(s), and optional notes. Title, cycle and publication consent exist in
the payload but are hidden in the current public UI.   

**According to ai assistant:** "Authenticated users' product
name is supplied from their DPG account and made read-only.": If this is actually true, it is great news. 

**Autofill:**

- Product name: strong when it comes from the authenticated DPG product record;
  otherwise suggest from repository/website metadata for confirmation.
- Version: strong only when a tagged release or authoritative release page clearly
  identifies a current version. Leave blank for unversioned products.
- Visibility and all assessor details: user-only. These are account/workflow
  choices, not public product facts.

**Validation:** validate repository and website ownership only as a consistency
signal. Do not infer that an assessor is authorized from a public profile.

### 2. Governance

**Capabilities:** transparent owner/steward, public roadmap/decisions, community
input, articulated governance model, formal governance, and documented/practiced
roles. The form also has a public governance-document link and public decision-log
link. MED requires transparent ownership plus public roadmap/decisions; HIGH also
requires formal structures, documented/practiced roles and the governance document.

**Autofill:** strong for candidate evidence links to governance, steering,
maintainer and decision documents; draft-only for capability selections. Repository
ownership, a `GOVERNANCE.md`, public meeting notes and roadmap pages are useful
signals, but do not prove actual practice or formal authority.

**Validation:** strong for URL accessibility and whether the document discusses
governance/decisions. Flag documents without an identified owner, date, decision
process or relevant scope. Human review must decide whether governance is actually
transparent and practiced.

### 3. Secure Development & Deployment

**Capabilities:** security/privacy in design, release process, systematic secure
development, manual scans, automated SAST, automated DAST/dependency scanning and
a secure-coding checklist. Evidence fields are a security-policy link and CI
security-scan logs. MED requires systematic practices plus manual scans; HIGH
requires automated SAST, checklist and policy.

**Autofill:**

- Strong candidates: `SECURITY.md`, secure-development documentation, CI workflow
  files explicitly running SAST/dependency/DAST tools, release documentation, and
  public scan artifacts.
- Draft-only: selections for systematic practice, manual scans and checklist use.
- deps.dev: provide dependency/advisory observations as context only. Do not map a
  dependency vulnerability result directly to a capability checkbox or maturity
  score.

**Validation:** inspect CI configuration and public artifacts for named tools,
repository/branch scope and recent runs. A policy page is relevant evidence, but is
not evidence that scans execute. Public scan logs may expose sensitive information;
support private evidence and reviewer confirmation.

### 4. Regulatory Data Compliance

**Capabilities:** acknowledged requirements, guidance, target-market analysis,
implementer support, robust framework and tracked regulatory updates. Evidence is
a compliance-document link and a regulatory-change log. This indicator can be
marked out of scope with an explanatory note. HIGH requires framework, update
tracking and documentation.

**Autofill:** candidate privacy/compliance pages and jurisdiction references can be
found from documentation. Capability selections should be draft-only or blank.
Whether regulation applies depends on deployment, data categories and target market,
which public repository material often cannot establish.

**Validation:** test whether a submitted document addresses the named product,
relevant jurisdiction and current requirements; flag generic legal pages. Do not
automatically accept legal compliance or out-of-scope claims.

### 5. Security Controls

**Capabilities:** guidance, encryption guidance/defaults, RBAC, architecture and
independent audit. Evidence is an audit report/attestation, audit date and security
guidance link. The indicator can be out of scope. HIGH requires an independent
audit, report/attestation and a date within the prior 12 months.

**Autofill:** strong candidates for security-guidance and architecture links;
draft-only candidates for encryption/RBAC based on documentation and configuration.
Do not infer an independent audit from a badge, a security policy or a code scan.

**Validation:** extract audit issuer, covered product/version, scope and date where
the report is public. Check the provided date against the 12-month gate. Mark an
unavailable audit as `unverifiable/private`, not invalid. Human review is required
for audit independence and adequacy.

### 6. Open Standards

**Capabilities:** UI export, APIs, APIs for key exchanges, co-design with
implementers, standards-based implementation and use across four or more
jurisdictions. Evidence is API documentation, selected standards and selected
jurisdictions. HIGH requires standards-based implementation, API documentation,
at least one selected standard and four jurisdictions.

**Autofill:** strong for public API documentation and explicit standards detected in
OpenAPI files, schemas, protocol/configuration documentation and product docs.
Draft-only for key-exchange APIs, co-design, standards-based use and jurisdiction
claims. Do not select a standard merely because a README mentions its name without
showing product use.

**Validation:** check that API documentation describes the product and that cited
standards are actually implemented or profiled. Jurisdiction claims require public
deployment evidence or product-owner confirmation; country selection cannot be
verified safely from general web mentions.

### 7. Product Roadmap

**Capabilities:** public feature requests, roadmap, release cycle, input forum,
transparent prioritization and impact-based decisions. Evidence is a public roadmap
link and backlog/prioritization examples. HIGH requires transparent prioritization
and a roadmap link.

**Autofill:** strong for public roadmap, issue tracker, release notes and discussion
links. Draft-only for transparent prioritization and impact-based decisions.

**Validation:** verify that the resource is public, current and product-specific;
look for roadmap/release content and prioritization rationale. An issue list alone
does not prove the project accepts or prioritizes user input.

### 8. Source Code Accessibility

**Capabilities:** public repository, OSI-approved license, developer docs,
readable/structured code, extensibility without fork and active contribution
process. Evidence is repository and contribution-documentation links. MED requires
public repository plus OSI license; HIGH requires extensibility without fork and a
repository link.

**Autofill:** this is the highest-confidence section. Repository visibility,
canonical URL, license file/SPDX identifier, contribution documentation, developer
documentation and extension/plugin interfaces can be collected automatically.
Readable code, no-fork extensibility and an active process remain draft-only
assessments.

**Validation:** resolve the repository, inspect the declared license against an
OSI-approved list, validate that contribution documentation is reachable, and cite
plugin/API extension evidence. A repository being public does not establish active
maintenance or legal ownership of every dependency.

### 9. Total Cost of Ownership

**Capabilities:** cost drivers, operational assumptions, budget guidance,
deployment/model basis, pilot estimates, annual-maintenance estimates and
end-user capacity-building costs. Evidence is TCO documentation and an example
calculation. This indicator can be out of scope. HIGH requires pilot and annual
maintenance estimates plus TCO documentation.

**Autofill:** usually weak. The collector may surface deployment guides, cloud
resource requirements, pricing pages and public cost calculators. It should suggest
links, not select cost-estimation capabilities.

**Validation:** assess whether a document actually provides the requested cost
element, is current and applies to the product's deployment model. Cost assumptions,
local implementation cost and capacity-building cost require owner confirmation or
private evidence.

### 10. Flexible Architecture

**Capabilities:** modularity, extension points, plug-and-play components,
independent deployment, composable design and microservices/equivalent. Evidence
is architecture documentation and extension/plugin examples. HIGH requires
composable design and architecture documentation.

**Autofill:** strong for architecture-documentation and plugin/extension example
links; draft-only for architectural capability selections. Source layout, Helm
charts, service definitions, module/plugin APIs and architecture decision records
are useful signals, but cannot alone establish operational independence.

**Validation:** check that the architecture document describes the current product
and that cited extension examples are real. Flag generic diagrams or obsolete docs.
The reviewer should decide whether the claimed architecture meets the indicator's
meaning.

### 11. Summary

The summary displays scores, bands, confidence, unmet gates and recommendations;
confidence from whether evidence fields are filled, not from link validity.

**Recommendation:** show a separate evidence-reliability breakdown beside, not
inside, the current capability score until governance agrees to change scoring.
For example: `AI-verified`, `AI-suggested and user-confirmed`, `self-declared`,
`private/unverifiable`, and `needs reviewer attention`. Do not silently reduce a
capability score solely because public evidence is unavailable.

## Recommended Delivery Scope

### MVP: high-confidence collection and basic validation

1. Ask for repository, product website and documentation URLs early in the flow.
2. Collect repository metadata, license, README, contribution/security files,
   releases, CI workflow names and likely public documentation links.
3. Pre-populate only high-confidence links and facts, especially Source Code
   Accessibility, documentation/API links, roadmap candidates and governance
   candidates.
4. Validate submitted public URLs for resolution, product relevance and indicator
   relevance, returning cited reasons.
5. Clearly distinguish AI suggestions, user-confirmed answers and validation
   results. Leave unsupported checkboxes unselected.

