"""Public MAT form snapshot used for evidence collection, not MAT writeback."""

from dataclasses import dataclass


VERSION = "mat-public-v1"
PILOT_SECTIONS = ("source_code", "governance", "flexible_architecture")


@dataclass(frozen=True)
class EvidenceField:
    id: str
    section: str
    label: str
    value_type: str
    strength: str
    search_terms: str


@dataclass(frozen=True)
class Capability:
    id: str
    section: str
    label: str


EVIDENCE_FIELDS = (
    EvidenceField("ev_gov_public_governance_doc", "governance", "Public governance document", "url", "strong", "governance model steering committee decision log"),
    EvidenceField("ev_gov_public_decision_log", "governance", "Public decision log", "url", "basic", "governance decisions roadmap"),
    EvidenceField("ev_sdlc_security_policy", "secure_development", "Security policy document", "url", "strong", "security policy secure development"),
    EvidenceField("ev_sdlc_ci_security_logs", "secure_development", "CI security scan logs", "url", "basic", "GitHub Actions security scan SAST dependency"),
    EvidenceField("ev_reg_compliance_docs", "regulatory_compliance", "Compliance documentation", "url", "strong", "compliance GDPR data protection"),
    EvidenceField("ev_reg_change_log", "regulatory_compliance", "Regulatory change log", "text", "basic", "regulatory compliance changelog"),
    EvidenceField("ev_secctrl_audit_report_or_attestation", "security_controls", "Audit report or attestation", "url", "strong", "security audit attestation"),
    EvidenceField("ev_secctrl_security_guidance_link", "security_controls", "Security guidance link", "url", "basic", "security guidance encryption RBAC"),
    EvidenceField("ev_os_api_docs", "open_standards", "API documentation", "url", "strong", "API documentation OpenAPI standards"),
    EvidenceField("ev_roadmap_public_link", "product_roadmap", "Public roadmap link", "url", "strong", "public roadmap releases feature requests"),
    EvidenceField("ev_backlog_examples", "product_roadmap", "Backlog or prioritization examples", "text", "basic", "backlog prioritization issues"),
    EvidenceField("ev_src_repo_link", "source_code", "Repository link", "url", "strong", "source repository GitHub GitLab"),
    EvidenceField("ev_src_contrib_docs", "source_code", "Contribution documentation", "url", "basic", "CONTRIBUTING developer documentation"),
    EvidenceField("ev_tco_doc_link", "total_cost_ownership", "TCO documentation link", "url", "strong", "total cost ownership deployment cost"),
    EvidenceField("ev_tco_example_calc", "total_cost_ownership", "Example cost calculation", "url", "basic", "cost calculator budget estimate"),
    EvidenceField("ev_architecture_docs", "flexible_architecture", "Architecture documentation", "url", "strong", "architecture modular microservices extensibility"),
    EvidenceField("ev_extension_examples", "flexible_architecture", "Extension plugin examples", "text", "basic", "plugins extensions modules"),
)


CAPABILITIES = (
    Capability("gov_owner_transparent", "governance", "Product owner or steward is transparent and accessible"),
    Capability("gov_governance_articulated", "governance", "Governance model is articulated"),
    Capability("gov_formal_structures_exist", "governance", "Formal governance structures exist"),
    Capability("sdlc_systematic_secure_practices", "secure_development", "Systematic secure development practices followed"),
    Capability("sdlc_automated_sast", "secure_development", "Automated SAST"),
    Capability("sdlc_automated_dast_or_dep_scan", "secure_development", "Automated DAST or dependency scanning"),
    Capability("reg_analyzed_for_target_market", "regulatory_compliance", "Compliance analyzed for target markets"),
    Capability("reg_framework_robust", "regulatory_compliance", "Robust compliance framework in place"),
    Capability("secctrl_guidance_exists", "security_controls", "Security guidance documentation exists"),
    Capability("secctrl_independent_audit_12m", "security_controls", "Independent security audit within 12 months"),
    Capability("os_some_apis_exist", "open_standards", "Some APIs exist for data exchange"),
    Capability("os_sdo_standards_based", "open_standards", "Based on standards-development-organization standards"),
    Capability("roadmap_public_feature_requests", "product_roadmap", "Public feature request process exists"),
    Capability("roadmap_exists", "product_roadmap", "Product roadmap exists and is accessible"),
    Capability("src_public_repo", "source_code", "Public source-code repository exists"),
    Capability("src_osi_license", "source_code", "OSI-approved open-source license"),
    Capability("src_contribution_process", "source_code", "Contribution process documented and active"),
    Capability("tco_budget_guidance_high_level", "total_cost_ownership", "High-level budget guidance provided"),
    Capability("tco_annual_maintenance_estimates", "total_cost_ownership", "Annual maintenance cost estimates"),
    Capability("arch_some_modularity", "flexible_architecture", "Some modularity exists"),
    Capability("arch_composable_by_design", "flexible_architecture", "Composable by design"),
    Capability("arch_microservices_or_equivalent", "flexible_architecture", "Microservices or equivalent architecture"),
)


def selected_evidence_fields(requested: list[str]) -> tuple[EvidenceField, ...]:
    if requested == ["all"]:
        return EVIDENCE_FIELDS
    wanted = set(requested)
    return tuple(field for field in EVIDENCE_FIELDS if field.id in wanted)


def selected_capabilities(requested: list[str]) -> tuple[Capability, ...]:
    if requested == ["all"]:
        return CAPABILITIES
    wanted = set(requested)
    return tuple(capability for capability in CAPABILITIES if capability.id in wanted)


def three_section_pilot_indicators() -> list[str]:
    """Return the public MAT fields covered by the bounded investigation pilot."""
    return [
        *(field.id for field in EVIDENCE_FIELDS if field.section in PILOT_SECTIONS),
        *(capability.id for capability in CAPABILITIES if capability.section in PILOT_SECTIONS),
    ]
