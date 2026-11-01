# DPG Nomination and Maturity Assessment: Shared Evidence Opportunities

## Purpose

The DPG nomination form and the Maturity Assessment Tool (MAT) should use one
shared evidence-collection and validation capability, not two separate AI
integrations. Both ask product owners to locate public evidence, make claims about
the product, and provide links that reviewers must assess.

The two forms are not interchangeable:

- The nomination form assesses whether a product meets DPG Standard indicators.
- MAT assesses maturity against more granular capability choices, evidence fields
  and MED/HIGH gates.

The shared system should therefore collect facts and validate evidence once, while
mapping those facts to each form's own fields and review rules.

This document compares the prior nomination-form proposal
(`dpg-nomination-form-autofill-proposal.md`) with the public MAT assessment flow.
It recommends what to build first for Epic #26, AI-Aided Evidence Collection &
Validation for MAT.

## Shared Product Model

### One evidence record, many form mappings

Every collected or submitted item should be stored as an evidence record with:

- source type: repository API, repository file, documentation page, website page,
  deps.dev response, submitted URL, uploaded document or private declaration;
- canonical URL/path, retrieval time and content hash where possible;
- title, content type, language and source excerpt;
- extracted facts and confidence;
- technical/relevance validation result and rationale;
- mappings to one or more nomination or MAT fields;
- owner confirmation and reviewer decision, kept separate from AI output.

This avoids fetching the same `LICENSE`, API reference or governance page multiple

### One vocabulary for evidence status

Both forms should use the same evidence state vocabulary:

| Status | Meaning |
| --- | --- |
| `ai_suggested` | Public evidence was discovered but the product owner has not confirmed the form value |
| `user_confirmed` | Owner accepted or supplied the evidence/claim |
| `ai_verified` | URL/document was reachable and its content was relevant to the specific field |
| `questionable` | Link works but evidence is incomplete, stale, generic or conflicts with the claim |
| `invalid` | Broken, inaccessible, irrelevant or clearly mismatched evidence |
| `private_unverifiable` | Owner declares evidence exists but it cannot be publicly checked |
| `human_reviewed` | Reviewer made an explicit decision |

`ai_verified` must mean relevance, not independent proof that an organization
follows every policy it publishes.

## Overlap Map

| Shared evidence area | Nomination form use | MAT use | Automation value |
| --- | --- | --- | --- |
| Product identity and public URLs | General Information | Assessment Details | High for URLs/name; owner/assessor details remain user-only |
| License and repository | Open Licensing | Source Code Accessibility | Very high; collect license file/SPDX, canonical repository and public visibility |
| Documentation and developer guidance | Documentation | Source Code Accessibility, Secure Development, Flexible Architecture | High for links; moderate for quality/practice claims |
| Governance and ownership | Clear Ownership | Governance, Product Roadmap | Moderate; documents/links are discoverable but actual accountability/practice needs review |
| APIs, export and interoperability | Mechanism for Extracting Data, Standards & Best Practices | Open Standards | High for API docs and named standards; moderate/low for actual deployments and co-design claims |
| Platform independence and architecture | Platform Independence | Flexible Architecture | Moderate; architecture evidence can be found but conclusions require interpretation |
| Privacy, security and legal controls | Privacy & Applicable Laws, Data Privacy & Security | Regulatory Data Compliance, Security Controls, Secure Development & Deployment | Moderate for evidence discovery; low for full verification because audit/scope/private controls matter |
| Community safety and contribution policy | Inappropriate & Illegal Content, Protection from Harassment | Governance, Source Code Accessibility | Moderate where code of conduct/moderation policies are public; product behavior needs review |
| Adoption, deployments and cost | Scale of Solution | Total Cost of Ownership, Open Standards jurisdictions | Low to moderate; public case studies can be collected, but numbers/costs need confirmation |

## What Can Be Reused First

### 1. Repository and documentation evidence collector

This is the best first shared component. It directly supports both forms and uses
public, retrievable sources:

- repository metadata and default branch;
- `README`, `LICENSE`, `CONTRIBUTING`, `SECURITY.md`, `GOVERNANCE.md`, code of
  conduct and release notes;
- CI workflow/configuration names and public artifacts;
- links discovered in repository documentation;
- bounded crawl of product and documentation sites;
- canonicalization and de-duplication of URLs.

Immediate field coverage:

- nomination: General Information, Open Licensing, Documentation;
- MAT: Source Code Accessibility, plus candidate links for Governance, Secure
  Development, Open Standards, Product Roadmap and Flexible Architecture.

This collector should be designed as evidence collection, not a general-purpose
scraper. It needs allowlisted hosts, bounded depth/page count, rate limiting,
timeouts, content-size limits and a cached response model.

### 2. Field-specific public URL validation

The next common component should validate any public evidence URL submitted in
either form:

1. resolve redirects and record final URL/status;
2. classify page/document type and extract readable content;
3. identify title, dates and product references;
4. compare the extracted content to the field's evidence requirement;
5. return status, cited excerpt and reason.

Examples:

- A license URL should contain a recognizable license, not merely link to a source
  repository.
- An API-documentation URL should describe usable product APIs, not a marketing
  page that says the product has an API.
- A security-policy URL should contain policy/process material; it is still not an
  audit report.

This delivers the Epic's most urgent correction: distinguish a completed evidence
field from credible, relevant evidence.

### 3. Shared field mapping and evidence guidance

Build a versioned configuration that maps evidence types to both systems:

```text
evidence type: public_repository
nomination fields: general_information.repository, open_licensing.source_link
MAT fields: source_code_accessibility.repository_link
validation rule: repository resolves and is public
```

The same configuration can provide user-facing guidance for strong versus basic
LLM prompts or frontend code.

### 4. Private evidence and reviewer queue

Private evidence is required in both systems, but it should follow the public URL
validator rather than precede it. Add a per-evidence-item declaration with optional
secure upload/reference and a clear `private_unverifiable` state. Reviewer queues
should prioritize:

- broken/irrelevant public evidence;
- high-score MAT gates relying on weak or private evidence;
- claims with no supporting public evidence;
- evidence that has changed or expired since its earlier validation.

## What Must Remain Form-Specific

### MAT scoring and gates

MAT capability weights, out-of-scope handling, evidence confidence and MED/HIGH
is relevant; MAT must decide whether that evidence meets a particular gate.

Do not make a public-document validation result silently change an assessment
score. First present evidence reliability separately. Any score weighting by
reliability tier needs an explicit product-policy decision, migration plan and
visible explanation.

### Nomination eligibility and review

The nomination portal's DPG Standard interpretation, owner eligibility and
reviewer decisions remain nomination-specific. A public license or documentation
page can be reused as evidence, but it does not make the submission eligible on
its own.

### Sensitive claims

Audits, legal compliance, security controls, deployment counts and TCO have
different implications in the two forms. The shared system should collect and
classify their evidence but must not overstate what a crawl, dependency scan or
LLM can establish.

## Recommended Work Order

### Phase 0: define evidence rules before writing integrations

Create a small, versioned indicator/evidence registry containing:

- form and field identifiers;
- expected evidence type and strong/basic guidance;
- extraction terms and source preferences;
- validation prompt/rule reference;
- private-evidence eligibility;
- human-review conditions.

Start with the jointly reusable fields below. This avoids producing two diverging
sets of prompts and lets reviewers understand why a suggestion was made.

### Phase 1: high-confidence public evidence

Implement the shared repository/document collector and mappings for:

1. repository URL, product metadata and license;
2. documentation and contribution links;
3. source-code accessibility;
4. public API/export and standards documentation;
5. governance and roadmap candidate links.

This gives the highest autofill value with the lowest risk of unsupported claims.
It also reuses the existing maturity-tool collector work rather than beginning with
an LLM-only design.

### Phase 2: public URL relevance validation

Add technical checks and field-specific relevance checks for the Phase 1 evidence.
Show results to the product owner before submission and to reviewers after
submission. Capture reason, cited excerpt and retrieval date.

For the first demo, an end-to-end path should use one representative field, for
example:

1. collect a public repository and `LICENSE`;
2. pre-populate nomination Open Licensing and MAT Source Code Accessibility;
3. let the owner confirm or edit it;
4. validate the submitted URL's reachability and license relevance;
5. display the result to a reviewer.

### Phase 3: security and architecture evidence discovery

Extend collection to `SECURITY.md`, CI security configuration, architecture docs,
plugins/modules and deps.dev package/dependency signals. These should produce
review cues and evidence candidates, not automatic maturity claims.

Important deps.dev constraint: it is useful only after identifying supported
packages/versions. It should not be described as a generic repository security
scanner or as proof of secure-development maturity.

### Phase 4: private evidence and reliability presentation

Add private-evidence declarations, secure reviewer access where needed, reviewer
queueing and a visible evidence-reliability breakdown. Only then evaluate whether
reliability tiers should affect either form's score.

### Phase 5: difficult and context-dependent areas

Handle legal/compliance, audit adequacy, deployment/adoption, jurisdiction claims,
TCO and product safety/moderation last. These require more user context, private
evidence and human judgment than source-code/documentation evidence.

## Risks and Controls

| Risk | Control |
| --- | --- |
| LLM invents a capability from weak text | Require citations; only auto-fill factual links; leave unsupported capability choices unselected |
| A valid URL is treated as proof | Separate reachability, relevance and human acceptance states |
| Stale public evidence remains trusted | Store retrieval dates/content hashes; revalidate before review or after a defined TTL |
| Private audit evidence is penalized | Use `private_unverifiable`, not `invalid`; route to authorized review |
| Different forms produce contradictory suggestions | Map both forms to the same underlying evidence record and preserve versioned rules |
| Crawling creates cost, rate-limit or security issues | Bound crawling, cache results, restrict schemes/hosts, sanitize extraction and never execute fetched content |
| Reliability tiers create opaque score changes | Display tiers first; change score formula only after agreed policy and explain every effect |

## Recommendation

Start with a shared evidence registry, repository/document collector and
field-specific URL relevance validator. These are valuable to both forms,
demonstrable before the November milestone, and directly address the pilot's
credibility concern. Delay automatic scoring consequences and broad legal/security
conclusions until there is a stable reviewer workflow and evidence policy.
