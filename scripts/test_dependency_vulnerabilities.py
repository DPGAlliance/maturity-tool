import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("collect_dependency_vulnerabilities.py")
SPEC = importlib.util.spec_from_file_location("dependency_vulnerabilities", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class DependencyParserTests(unittest.TestCase):
    def test_package_lock_classifies_direct_and_transitive_dependencies(self):
        dependencies = MODULE.parse_package_lock(
            '{"lockfileVersion": 3, "packages": {"": {"dependencies": {"direct": "1.0.0"}}, "node_modules/direct": {"version": "1.0.0"}, "node_modules/@scope/transitive": {"version": "2.0.0"}}}',
            "package-lock.json",
        )
        self.assertEqual(
            dependencies,
            [
                {"system": "NPM", "name": "direct", "version": "1.0.0", "path": "package-lock.json", "relationship": "direct"},
                {"system": "NPM", "name": "@scope/transitive", "version": "2.0.0", "path": "package-lock.json", "relationship": "transitive"},
            ],
        )

    def test_exact_version_parsers(self):
        self.assertEqual(MODULE.parse_go_sum("example.com/mod v1.2.3 h1:hash\nexample.com/mod v1.2.3/go.mod h1:hash\n", "go.sum"), [{"system": "GO", "name": "example.com/mod", "version": "v1.2.3", "path": "go.sum", "relationship": "unknown"}])
        self.assertEqual(MODULE.parse_requirements("requests==2.32.0\nDjango>=5\n", "requirements.txt"), [{"system": "PYPI", "name": "requests", "version": "2.32.0", "path": "requirements.txt", "relationship": "direct"}])
        self.assertEqual(MODULE.parse_cargo_lock('[[package]]\nname = "serde"\nversion = "1.0.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n', "Cargo.lock"), [{"system": "CARGO", "name": "serde", "version": "1.0.0", "path": "Cargo.lock", "relationship": "unknown"}])

    def test_merge_preserves_direct_classification_and_paths(self):
        merged = MODULE.merge_dependencies([
            MODULE.dependency("NPM", "example", "1.0.0", "a/package-lock.json", "transitive"),
            MODULE.dependency("NPM", "example", "1.0.0", "b/package-lock.json", "direct"),
        ])
        self.assertEqual(merged[0]["relationship"], "direct")
        self.assertEqual(merged[0]["paths"], ["a/package-lock.json", "b/package-lock.json"])


class VulnerabilityNormalizationTests(unittest.TestCase):
    def test_vulnerability_rows_only_include_advisories(self):
        dependency = {"system": "NPM", "name": "example", "version": "1.0.0", "paths": ["package-lock.json"], "relationship": "direct"}
        versions = {MODULE.version_cache_key(dependency): {"purl": "pkg:npm/example@1.0.0", "advisoryKeys": [{"id": "GHSA-test"}]}}
        rows = MODULE.vulnerability_rows("owner", "repo", [dependency], versions, {"GHSA-test": {"aliases": ["CVE-2026-1"], "title": "Test", "cvss3Score": 8.1}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "high")
        self.assertEqual(rows[0]["advisory_id"], "GHSA-test")

    def test_cvss_severity(self):
        self.assertEqual(MODULE.cvss_severity(9.0), "critical")
        self.assertEqual(MODULE.cvss_severity(7.0), "high")
        self.assertEqual(MODULE.cvss_severity(4.0), "medium")
        self.assertEqual(MODULE.cvss_severity(0.1), "low")
        self.assertEqual(MODULE.cvss_severity(None), "unknown")


if __name__ == "__main__":
    unittest.main()
