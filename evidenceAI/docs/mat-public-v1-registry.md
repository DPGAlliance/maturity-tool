# MAT Public V1 Registry

`mat-public-v1` is a versioned snapshot extracted from the public MAT wizard at
`https://maturity.digitalpublicgoods.net/assessments/new`. It is an EvidenceAI
collection aid, not a contract for MAT UI behavior or writeback.

The registry covers the nine scored sections: Governance, Secure Development &
Deployment, Regulatory Data Compliance, Security Controls, Open Standards,
Product Roadmap, Source Code Accessibility, Total Cost of Ownership, and
Flexible Architecture.

For every evidence field it stores the stable public field ID, section, label,
value type, evidence strength, and search vocabulary. Capabilities are separate
records because they affect scoring and must never be conflated with evidence
URLs or text drafts. The public snapshot excludes assessor/profile fields and
does not encode MAT acceptance or writeback behavior.
