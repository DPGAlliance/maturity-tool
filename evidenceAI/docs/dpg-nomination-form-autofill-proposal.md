# DPG Form Autofill API Proposal

## Summary

This is a small, lean backend project to help users fill out the Digital Public Goods submission form faster.

There is no need for a separate UI. The existing DPG website remains the user interface. The website can call a backend API that:
- accepts a repository URL and a project website URL
- fetches the relevant form instructions from GitHub/wiki pages
- reads the repository and website
- generates suggested answers for the current form page
- returns suggestions, confidence, and evidence back to the website

The goal is not full automation. The goal is to reduce manual work by pre-filling the easy and medium-difficulty sections and clearly flagging the rest for user review. Where the evidence is weak, the API should return a blank. Where the collected eveidence is not detailed enough the generated answer may state what was found, to ease the cognitive load on the user instead of a full answer.

## Proposed Approach

### 1. API Shape

A minimal API is enough.

Suggested endpoint:
- `POST /autofill`

Suggested input:
- `repo_url`
- `website_url`
- `section` or `page`
- optionally `application_id` or request correlation ID from the website

Suggested output:
- `section`
- `fields`
- `suggested_value`
- `confidence`
- `evidence`
- `status`

Example field status values:
- `filled`
- `partial`
- `needs_user_input`

### 2. Fetch -> Extract -> Generate Pipeline

The backend can stay small if it follows a strict pipeline:

1. Fetch
- current GitHub/wiki guidance for the relevant section
- repository metadata and key files like `README`, `LICENSE`, docs, config, API docs
- public website content

2. Extract
- pull out structured facts such as name, owner, license, docs links, standards references, export features, privacy links
- keep a small evidence bundle for each candidate field

3. Generate
- ask the LLM to produce only grounded suggestions
- require the model to cite evidence
- return blank or `needs_user_input` when evidence is weak

This is the key to keeping the project reliable and lean:
- do not let the model invent claims
- do not attempt full autonomous submission
- do not overbuild storage or workflows

### 3. Effort Estimate

This should be a small project if the scope stays tight.

A realistic MVP would focus on:
- fetching instructions
- reading repo and website inputs
- generating page-level suggestions
- returning confidence and evidence
- caching results for up to 30 days

## Storage and Caching

Long-term storage is not necessary.

A simple cache with roughly 30-day retention should be enough for:
- fetched GitHub/wiki guidance
- fetched repository summaries
- fetched website content
- generated autofill suggestions

This reduces repeated work and cost while keeping the implementation lightweight.

## Page-by-Page Feasibility

### 1. General Information
**Judgment:** This can be done. The user should provide the repo and website URLs, and the model can extract basic project information.

**Reason:** Project name, website, repository, short description, organization, and similar basics are usually available from the repo and public site.

### 2. SDG Relevance
**Judgment:** This can be done using the SDG definitions. With user supervision of course. We only proivde suggestions.

**Reason:** The model can infer relevant SDGs from the project purpose and documentation, but this is not simple extraction and should remain review-first.

### 3. Open Licensing
**Judgment:** This can be done.

**Reason:** License evidence is usually explicit in `LICENSE`, `README`, package metadata, or project documentation.

### 4. Clear Ownership
**Judgment:** This can mostly be done, but this one is somewhat more complicated.

**Reason:** Ownership may be inferable from organization pages and repository ownership, but legal ownership details are not always clearly stated.

### 5. Platform Independence
**Judgment:** This one seems somewhat complicated.

**Reason:** Demonstrating independence from closed platforms usually requires architecture-level reasoning and may not be explicitly documented.

### 6. Documentation
**Judgment:** This can be done.

**Reason:** Documentation links, install guides, user guides, API docs, and contribution docs are usually easy to discover.

### 7. Mechanism for Extracting Data
**Judgment:** This can often be done, but may require synthesis. Don't return if the evidence is weak.

**Reason:** Export and data access capabilities may be spread across API docs, technical docs, and website content.

### 8. Privacy & Applicable Laws
**Judgment:** This one seems complicated.

**Reason:** Privacy and legal compliance claims are often incomplete, vague, or only partially public.

### 9. Standards & Best Practices
**Judgment:** This is doable, but not always easy.

**Reason:** Standards may be inferable from APIs, schemas, or documentation, but best-practice claims often require interpretation.

### 10. Data Privacy & Security
**Judgment:** This one seems complicated.

**Reason:** Security controls and personal data handling are often only partially documented in public materials.

### 11. Inappropriate & Illegal Content
**Judgment:** This one may be complicated depending on the product.

**Reason:** If the product involves user-generated content, moderation policy matters; otherwise some parts may be not applicable or lightly documented.

### 12. Protection from Harassment
**Judgment:** This one may be complicated.

**Reason:** Relevant evidence may be spread across codes of conduct, moderation policies, community docs, or legal pages.

### 13. Scale of Solution
**Judgment:** This can often be partially done. But progably better to collect from user input.

**Reason:** Public adoption signals may be available, but hard usage numbers or institutional deployment details may need manual confirmation.

## Recommended MVP Scope

The MVP should focus on the sections where autofill is most reliable. Don't return where the evidence is weak, and leave those for user review.

Best candidates for strong autofill:
- General Information
- Open Licensing
- Documentation
- parts of Mechanism for Extracting Data
- parts of Scale of Solution

Best candidates for draft-only suggestions:
- SDG Relevance
- Clear Ownership
- Standards & Best Practices

Best candidates for conservative handling:
- Platform Independence
- Privacy & Applicable Laws
- Data Privacy & Security
- Inappropriate & Illegal Content
- Protection from Harassment

## Recommendation

This project is worth doing as a small API integration, not as a standalone product.

The lean version is:
- website stays the UI
- backend API does fetch/extract/generate
- 30-day cache
- page-by-page suggestions
- confidence + evidence returned with every suggestion
- unsupported claims left blank

That should be enough to make the form meaningfully easier to complete without turning this into a large engineering effort.
