# DPG Evidence Automation: Project Owner Feasibility Brief

## Summary

The MAT form collects repo and website info only at a later stage in the process. MAT evidence verification is marked as CRITICAL prio while the autofill for the nomination is only MEDIUM. But if we want the MAT fillout to be smooth and efficient, with pre-populated evidence, we need to collect what we can during the nomination stage: which if I understand correctly must happen before the MAT is opened.

The DPG nomination flow should be the first evidence-collection stage. By the
time a product owner opens the Maturity Assessment Tool (MAT), we should already
have collected and analysed the public repository, website, documentation and
evidence links supplied during nomination. MAT can then reuse that work to suggest
links and capability checkboxes instead of starting from a blank form.

Whether the actual autofill functionality is implemented or not, the nomination stage should still aim to collect as much relevant evidence as possible to facilitate later automation in the MAT. Based on this we may also _suggest evidence links_ for the user to review and confirm during the nomination process. As the user progresses with reviewing and populating the MAT evidence fields we can continuously validate the evidence and refine the pre-filled information, ensuring higher accuracy and reducing manual effort.

Suggesting evidence links may be problematic: should trigger validation based on what we collected? Should we wait for approval by the user, that complicates the UI/UX, or avoid the suggestion and just preload resources that may be relevant?
Risk: we may suggest lower value evidence that is publicly available, compared to what the user would provide themselves without a suggestion.

We should treat automation as **evidence collection and
suggestion**, not automatic assessment or approval.
Every automated result remains a suggestion:

- Product owners can accept, edit, replace or reject it.
- ATM Human Reviewers make the final decision.
- A confidence value helps the system prioritize suggestions, but never turns one
  into an accepted claim.

## What We Can Collect Automatically

The following public resources are realistic first sources, that we can build on before the MAT form is started. The Submitted evidence URLs should be integrated into the MAT evidence fields as they are collected.

| Resource | What we can look for |
| --- | --- |
| Public GitHub repository | Product metadata, README, LICENSE, releases, repository visibility, contribution/security/governance files, issue/discussion links, CI workflow names |
| Repository documentation | Developer documentation, architecture, plugin/extension examples, API links, deployment guidance, roadmap links |
| Product website and documentation site | Product description, owner/steward information, public roadmap, governance, API references, privacy/compliance/security/architecture pages |
| Submitted evidence URLs | Whether the resource opens and contains content relevant to the form field |
| deps.dev, when a supported package/version is identifiable | Dependency and published advisory signals; useful security context, not proof of security maturity |

For a roughly 60-second first pass, scope collection to the nominated repository,
the owner-provided website/documentation URLs, and direct links from their landing
pages. A broad crawl of arbitrary sites should continue in the background or be
avoided. This gives a predictable experience and avoids delays, rate-limit issues
and unreliable results.

## First Priority: Shared Nomination and MAT Fields

The table shows where public evidence can be collected, whether it can support an
automated suggestion, and whether a later relevance check is practical.

| Evidence area | Nomination page(s) | MAT page(s) | Can we suggest a value/checkbox? | Can we validate submitted evidence relevance? | Priority |
| --- | --- | --- | --- | --- | --- |
| Repository, product links and basic identity | General Information | Assessment Details; Source Code Accessibility | Yes for URLs/name; user confirms identity | Yes | High |
| Open-source license | Open Licensing | Source Code Accessibility | Yes when a recognizable license is present | Yes | High |
| Documentation and contribution guidance | Documentation | Source Code Accessibility | Yes for documentation/contribution links; checkbox suggestions are reasonable | Yes | High |
| API, export and standards material | Mechanism for Extracting Data; Standards & Best Practices | Open Standards | Yes for API documentation and named standards; suggest capability choices cautiously | Yes | High |
| Governance, owner/steward and public decisions | Clear Ownership | Governance | Yes for candidate documents/links; capability boxes remain suggestions | Yes | Medium |
| Public roadmap and release process | Documentation / project information | Product Roadmap | Yes for roadmap, release notes and issue-tracker links; suggest boxes cautiously | Yes | Medium |
| Architecture and extensibility | Platform Independence | Flexible Architecture | Yes for architecture/plugin evidence; architecture boxes remain suggestions | Yes | Medium |
| Security policy and public CI security evidence | Data Privacy & Security | Secure Development & Deployment; Security Controls | Yes for security policy and visible CI evidence; do not infer audits or actual practice | Yes, but only for relevance | Medium |
| Privacy, compliance and legal material | Privacy & Applicable Laws | Regulatory Data Compliance | Suggest links only; do not confidently select compliance boxes | Yes, but legal adequacy needs humans | Low |
| Cost, deployment scale and jurisdictions | Scale of Solution | Total Cost of Ownership; Open Standards | Usually suggest links only | Partly; numbers and costs need confirmation | Low |
| Safety, moderation and harassment protection | Inappropriate & Illegal Content; Protection from Harassment | No direct MAT equivalent | Candidate policies can be found | Partly | Later |

## What "Autofill" Should Mean

Autofill should not silently write final answers. The frontend should display a
separate visual state for suggested values and suggested checkboxes.

Example:

1. The collector finds `LICENSE`, `CONTRIBUTING.md` and a public repository.
2. It suggests the relevant Open Licensing and Source Code Accessibility answers.
3. The product owner accepts, edits or replaces those suggestions.
4. The final answer and its evidence are checked again before reviewer use.

Some evidence is sufficient for a strong suggestion:

- a public repository link;
- a recognizable open-source license;
- a public API reference;
- a public roadmap or contribution guide.

Other evidence only justifies a candidate link or cautious checkbox suggestion:

- governance in practice;
- secure development practice;
- architectural composability;
- compliance with a specific law;
- active use across jurisdictions;
- TCO and deployment claims;
- existence and independence of a security audit.

The system should leave a checkbox unselected when public evidence is weak. It can
still show the discovered resource to reduce the owner's research effort.

## Validation: First Scope

The initial validation goal is **relevance**, not certification.

For each final public evidence URL, we can check:

1. Does it open and can its content be read?
2. Is it about the claimed product?
3. Does it contain material relevant to this specific field?
4. Is it obviously stale, generic or mismatched?

The product owner can receive a simple result:

- `Evidence appears relevant`
- `Evidence needs attention`

The reviewer should receive the detailed explanation, source excerpt, retrieval
date and internal validation strength. A public policy can be relevant without
proving that the organization follows it; the reviewer remains responsible for that
judgment.

Private material, such as an audit report, should be represented as
`private_not_publicly_verifiable`. It must not be treated as either publicly
validated or invalid merely because it cannot be fetched.

## Recommended Order

1. **Start with nomination evidence collection.** Build the shared record of
   repositories, websites, documents, submitted links and extracted facts.
2. **Prioritize high-confidence overlap:** license, public repository,
   documentation/contribution links, API/standards documentation, governance and
   roadmap links.
3. **Use this evidence to suggest MAT answers.** Suggestions are visible and
   editable, never final.
4. **Add relevance validation for submitted public URLs.** This directly addresses
   the current problem that evidence completion is not evidence credibility.
5. **Add difficult areas later:** audits, compliance, security practice, cost,
   deployment scale and jurisdiction claims.

## Important Design Requirement

The mapping from a resource to a form field will become complex. One API document
may support nomination data-extraction/standards answers and MAT Open Standards;
one repository may support licensing, source accessibility, governance and roadmap
suggestions.

We should explicitly invest in making the field-to-evidence mapping readable,
versioned and extensible. This is more important than producing a large number of
one-off prompts. It lets the team explain why a suggestion was made, add indicators
without rewriting the collector, and keep nomination and MAT consistent.

## Recommendation

Proceed with shared nomination-first evidence collection and the high-priority
overlap fields. The near-term objective is credible, reviewable suggestions that
save product-owner time. Do not promise automated approval, legal compliance,
security assurance or an automatic maturity score.
