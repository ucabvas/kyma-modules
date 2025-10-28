#!/usr/bin/env python3
"""
Kyma Module Helm Chart Generator

Generates Helm charts from Kyma module manifests by:
1. Splitting CRDs from other resources
2. Converting custom resources to templated values.yaml
3. Creating standard Helm chart structure
4. Tracking upstream versions
"""

import sys
import yaml
import re
import argparse
import urllib.request
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


# No custom YAML dumper needed - we preserve original formatting by keeping text as-is


class ManifestDownloader:
    """Download manifests from GitHub releases"""

    def __init__(self, repo: str, manifests_dir: Path):
        self.repo = repo
        self.manifests_dir = manifests_dir
        self.api_base = "https://api.github.com"

    def get_latest_release(self) -> Optional[Dict[str, Any]]:
        """Get the latest release information from GitHub"""
        url = f"{self.api_base}/repos/{self.repo}/releases/latest"
        try:
            with urllib.request.urlopen(url) as response:
                return json.loads(response.read())
        except Exception as e:
            print(f"  ⚠️  Failed to get latest release: {e}")
            return None

    def download_file(self, url: str, output_path: Path) -> bool:
        """Download a file from URL to output path"""
        try:
            print(f"    Downloading {output_path.name}...")
            with urllib.request.urlopen(url) as response:
                content = response.read()
                with open(output_path, 'wb') as f:
                    f.write(content)
            return True
        except Exception as e:
            print(f"    ⚠️  Failed to download {output_path.name}: {e}")
            return False

    def download_manifest(self, filename: str) -> Optional[Path]:
        """Download a specific manifest file from the latest release"""
        release = self.get_latest_release()
        if not release:
            return None

        # Look for the file in release assets
        assets = release.get('assets', [])
        for asset in assets:
            if asset['name'] == filename:
                output_path = self.manifests_dir / filename
                if self.download_file(asset['browser_download_url'], output_path):
                    return output_path
                return None

        # If not in assets, try to construct direct download URL
        # Format: https://github.com/{repo}/releases/download/{tag}/{filename}
        tag = release.get('tag_name')
        if tag:
            url = f"https://github.com/{self.repo}/releases/download/{tag}/{filename}"
            output_path = self.manifests_dir / filename
            if self.download_file(url, output_path):
                return output_path

        print(f"    ⚠️  File {filename} not found in release")
        return None

    def download_manifests(self, manager_file: str, cr_file: Optional[str] = None) -> tuple[Optional[Path], Optional[Path]]:
        """Download both manager and CR manifests"""
        print(f"  📥 Downloading manifests from {self.repo}...")

        manager_path = self.download_manifest(manager_file)
        cr_path = None

        if cr_file:
            cr_path = self.download_manifest(cr_file)

        return manager_path, cr_path


class ManifestParser:
    """Parse and categorize Kubernetes manifests while preserving original formatting"""

    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.crd_docs: List[str] = []  # Raw YAML text
        self.resource_docs: List[str] = []  # Raw YAML text
        self.resource_kinds: List[str] = []  # Track kinds for each resource
        self.all_docs: List[Dict[str, Any]] = []  # Parsed for metadata only

    def parse(self) -> None:
        """Parse multi-document YAML and categorize resources by text"""
        with open(self.manifest_path, 'r') as f:
            content = f.read()

        # Split by document separator
        raw_docs = content.split('\n---\n')

        for raw_doc in raw_docs:
            raw_doc = raw_doc.strip()
            if not raw_doc:
                continue

            # Parse just to check the kind
            try:
                doc = yaml.safe_load(raw_doc)
                if not doc or not isinstance(doc, dict):
                    continue

                self.all_docs.append(doc)

                kind = doc.get('kind', '')
                if kind == 'CustomResourceDefinition':
                    self.crd_docs.append(raw_doc)
                else:
                    self.resource_docs.append(raw_doc)
                    self.resource_kinds.append(kind)
            except yaml.YAMLError:
                # Skip invalid YAML
                continue

    def get_version_from_images(self) -> Optional[str]:
        """Extract version from container images in resources"""
        for doc in self.all_docs:
            if doc.get('kind') in ['Deployment', 'StatefulSet', 'DaemonSet']:
                spec = doc.get('spec', {})
                template = spec.get('template', {})
                containers = template.get('spec', {}).get('containers', [])

                for container in containers:
                    image = container.get('image', '')
                    # Try to extract version from image tag
                    match = re.search(r':v?(\d+\.\d+\.\d+)', image)
                    if match:
                        return match.group(1)
        return None


class CustomResourceConverter:
    """Convert Custom Resource to Helm values"""

    def __init__(self, cr_path: Path):
        self.cr_path = cr_path
        self.cr_doc: Optional[Dict[str, Any]] = None

    def parse(self) -> None:
        """Parse the custom resource YAML"""
        with open(self.cr_path, 'r') as f:
            docs = list(yaml.safe_load_all(f))
            # Get the first non-empty document
            self.cr_doc = next((doc for doc in docs if doc), None)

    def extract_spec(self) -> Dict[str, Any]:
        """Extract spec from CR for values.yaml"""
        if not self.cr_doc:
            return {}

        return {
            'apiVersion': self.cr_doc.get('apiVersion', ''),
            'kind': self.cr_doc.get('kind', ''),
            'metadata': {
                'name': self.cr_doc.get('metadata', {}).get('name', ''),
                'namespace': '{{ .Release.Namespace }}',
            },
            'spec': self.cr_doc.get('spec', {})
        }

    def generate_values(self) -> Dict[str, Any]:
        """Generate values.yaml content"""
        spec_data = self.extract_spec()

        return {
            'customResource': {
                'enabled': True,
                'metadata': spec_data.get('metadata', {}),
                'spec': spec_data.get('spec', {})
            }
        }


class HelmChartGenerator:
    """Generate complete Helm chart structure"""

    def __init__(self,
                 module_name: str,
                 module_config: Dict[str, Any],
                 manifests_dir: Path,
                 output_dir: Path,
                 templates_dir: Path = Path('templates')):
        self.module_name = module_name
        self.module_config = module_config
        self.manifests_dir = manifests_dir
        self.output_dir = output_dir
        self.chart_dir = output_dir / module_name
        self.templates_dir = templates_dir

    def generate(self, download: bool = False) -> None:
        """Generate the complete Helm chart"""
        print(f"Generating chart for {self.module_name}...")

        # Download manifests if requested
        manager_path = self.manifests_dir / self.module_config['manager_file']
        cr_path = None

        if download:
            downloader = ManifestDownloader(
                repo=self.module_config['repo'],
                manifests_dir=self.manifests_dir
            )
            manager_path, cr_path = downloader.download_manifests(
                manager_file=self.module_config['manager_file'],
                cr_file=self.module_config.get('cr_file')
            )
            if not manager_path:
                print(f"  ⚠️  Failed to download manager manifest")
                return
        else:
            # Use existing files
            if not manager_path.exists():
                print(f"  ⚠️  Manager file not found: {manager_path}")
                return

            if self.module_config.get('cr_file'):
                cr_path = self.manifests_dir / self.module_config['cr_file']
                if not cr_path.exists():
                    print(f"  ⚠️  CR file not found: {cr_path}")
                    cr_path = None

        # Parse manager manifest
        parser = ManifestParser(manager_path)
        parser.parse()

        # Parse custom resource if exists
        cr_values = {}
        cr_data = None
        if cr_path and cr_path.exists():
            converter = CustomResourceConverter(cr_path)
            converter.parse()
            cr_values = converter.generate_values()
            cr_data = converter.extract_spec()

        # Create chart directory structure
        self._create_directories()

        # Generate Chart.yaml
        upstream_version = parser.get_version_from_images()
        self._generate_chart_yaml(upstream_version)

        # Generate CRDs
        self._generate_crds(parser.crd_docs)

        # Generate templates
        self._generate_manager_template(parser.resource_docs, parser.resource_kinds)
        if cr_data:
            self._generate_cr_template(cr_data)
        self._generate_helpers()

        # Generate values.yaml
        self._generate_values(cr_values)

        # Generate .helmignore
        self._generate_helmignore()

        print(f"  ✅ Chart generated at: {self.chart_dir}")

    def _create_directories(self) -> None:
        """Create chart directory structure"""
        (self.chart_dir / 'crds').mkdir(parents=True, exist_ok=True)
        (self.chart_dir / 'templates').mkdir(parents=True, exist_ok=True)

    def _generate_chart_yaml(self, upstream_version: Optional[str]) -> None:
        """Generate Chart.yaml"""
        chart_data = {
            'apiVersion': 'v2',
            'name': self.module_name,
            'description': self.module_config.get('description', f'Helm chart for Kyma {self.module_name} module'),
            'type': 'application',
            'version': self.module_config.get('chart_version', '1.0.0'),
            'appVersion': upstream_version or '0.0.0',
            'keywords': ['kyma', 'kyma-project', self.module_name],
            'home': f"https://github.com/{self.module_config['repo']}",
            'sources': [f"https://github.com/{self.module_config['repo']}"],
            'maintainers': [
                {
                    'name': 'Kyma Project',
                    'url': 'https://kyma-project.io'
                }
            ],
            'annotations': {
                'upstream-repo': self.module_config['repo'],
                'upstream-version': upstream_version or 'unknown',
                'generated-date': datetime.utcnow().isoformat() + 'Z'
            }
        }

        with open(self.chart_dir / 'Chart.yaml', 'w') as f:
            yaml.dump(chart_data, f, default_flow_style=False, sort_keys=False)

    def _generate_crds(self, crd_docs: List[str]) -> None:
        """Generate CRD files from raw YAML text"""
        if not crd_docs:
            print(f"  ℹ️  No CRDs found")
            return

        for idx, crd_text in enumerate(crd_docs):
            # Parse just to get the name
            try:
                crd = yaml.safe_load(crd_text)
                crd_name = crd.get('metadata', {}).get('name', f'crd-{idx}')
            except:
                crd_name = f'crd-{idx}'

            filename = f"{crd_name}.yaml"

            with open(self.chart_dir / 'crds' / filename, 'w') as f:
                f.write(crd_text)
                f.write('\n')

        print(f"  ✅ Generated {len(crd_docs)} CRD(s)")

    def _generate_manager_template(self, resource_docs: List[str], resource_kinds: List[str]) -> None:
        """Generate manager template from raw YAML text, preserving original formatting"""
        if not resource_docs:
            return

        template_path = self.chart_dir / 'templates' / 'manager.yaml'
        namespace_labels = self.module_config.get('namespace_labels', {})

        with open(template_path, 'w') as f:
            # Add Helm template header
            f.write('{{- if .Values.manager.enabled }}\n')

            for idx, resource_text in enumerate(resource_docs):
                f.write('---\n')

                # Check if this is a Namespace resource and we have labels to add
                kind = resource_kinds[idx] if idx < len(resource_kinds) else ''
                if kind == 'Namespace' and namespace_labels:
                    # Parse the Namespace resource to add labels
                    doc = yaml.safe_load(resource_text)

                    # Ensure metadata.labels exists
                    if 'metadata' not in doc:
                        doc['metadata'] = {}
                    if 'labels' not in doc['metadata']:
                        doc['metadata']['labels'] = {}

                    # Merge in the configured labels
                    doc['metadata']['labels'].update(namespace_labels)

                    # Re-serialize the modified Namespace
                    modified_text = yaml.dump(doc, default_flow_style=False, sort_keys=False)

                    # Escape {{ and }} in the modified YAML
                    escaped_text = modified_text.replace('{{', '__OPENBRACES__').replace('}}', '__CLOSEBRACES__')
                    escaped_text = escaped_text.replace('__OPENBRACES__', '{{ "{{" }}').replace('__CLOSEBRACES__', '{{ "}}" }}')
                    f.write(escaped_text)
                else:
                    # Escape {{ and }} in the YAML content so Helm won't try to parse them
                    # Use temporary placeholders to avoid re-escaping our escapes
                    escaped_text = resource_text.replace('{{', '__OPENBRACES__').replace('}}', '__CLOSEBRACES__')
                    escaped_text = escaped_text.replace('__OPENBRACES__', '{{ "{{" }}').replace('__CLOSEBRACES__', '{{ "}}" }}')
                    f.write(escaped_text)

                f.write('\n')

            f.write('{{- end }}\n')

        print(f"  ✅ Generated manager template with {len(resource_docs)} resource(s)")

    def _generate_cr_template(self, cr_data: Dict[str, Any]) -> None:
        """Generate templated custom resource from template file"""
        # Read template
        template_file = self.templates_dir / 'custom-resource.yaml'
        with open(template_file, 'r') as f:
            template = f.read()

        # Prepare spec section
        spec_section = ''
        if cr_data.get('spec'):
            spec_section = 'spec:\n{{- toYaml .Values.customResource.spec | nindent 2 }}'

        # Substitute placeholders
        content = template.replace('{api_version}', cr_data.get('apiVersion', ''))
        content = content.replace('{kind}', cr_data.get('kind', ''))
        content = content.replace('{name}', cr_data.get('metadata', {}).get('name', 'default'))
        content = content.replace('{spec_section}', spec_section)

        # Write output
        output_path = self.chart_dir / 'templates' / 'custom-resource.yaml'
        with open(output_path, 'w') as f:
            f.write(content)

        print(f"  ✅ Generated custom resource template")

    def _generate_helpers(self) -> None:
        """Generate _helpers.tpl from template file"""
        # Read template
        template_file = self.templates_dir / '_helpers.tpl'
        with open(template_file, 'r') as f:
            template = f.read()

        # Substitute module name
        content = template.replace('{module_name}', self.module_name)

        # Write output
        output_path = self.chart_dir / 'templates' / '_helpers.tpl'
        with open(output_path, 'w') as f:
            f.write(content)

        print(f"  ✅ Generated _helpers.tpl")

    def _generate_values(self, cr_values: Dict[str, Any]) -> None:
        """Generate values.yaml"""
        values = {
            'manager': {
                'enabled': True,
            },
        }

        # Add CR values if present
        if cr_values:
            values.update(cr_values)
        else:
            values['customResource'] = {
                'enabled': False
            }

        # Add common overrides
        values['nameOverride'] = ''
        values['fullnameOverride'] = ''

        with open(self.chart_dir / 'values.yaml', 'w') as f:
            f.write('# Default values for ' + self.module_name + '\n')
            f.write('# This is a YAML-formatted file.\n')
            f.write('# Declare variables to be passed into your templates.\n\n')
            yaml.dump(values, f, default_flow_style=False, sort_keys=False)

        print(f"  ✅ Generated values.yaml")

    def _generate_helmignore(self) -> None:
        """Generate .helmignore from template file"""
        # Read template
        template_file = self.templates_dir / 'helmignore.txt'
        with open(template_file, 'r') as f:
            content = f.read()

        # Write output
        output_path = self.chart_dir / '.helmignore'
        with open(output_path, 'w') as f:
            f.write(content)


def load_modules_config(config_path: Path) -> Dict[str, Any]:
    """Load modules configuration from YAML"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description='Generate Helm charts from Kyma module manifests'
    )
    parser.add_argument(
        '--config',
        type=Path,
        default=Path('modules.yaml'),
        help='Path to modules configuration file'
    )
    parser.add_argument(
        '--manifests-dir',
        type=Path,
        default=Path('.'),
        help='Directory containing module manifests'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('charts'),
        help='Output directory for generated charts'
    )
    parser.add_argument(
        '--module',
        type=str,
        help='Generate chart for specific module only'
    )
    parser.add_argument(
        '--download',
        action='store_true',
        help='Download latest manifests from GitHub releases before generating'
    )

    args = parser.parse_args()

    # Load configuration
    if not args.config.exists():
        print(f"Error: Configuration file not found: {args.config}")
        sys.exit(1)

    config = load_modules_config(args.config)
    modules = config.get('modules', [])

    if not modules:
        print("Error: No modules defined in configuration")
        sys.exit(1)

    # Filter modules if specific module requested
    if args.module:
        modules = [m for m in modules if m['name'] == args.module]
        if not modules:
            print(f"Error: Module '{args.module}' not found in configuration")
            sys.exit(1)

    # Generate charts
    print(f"\n{'='*60}")
    print(f"Kyma Module Helm Chart Generator")
    if args.download:
        print(f"Mode: Download latest from GitHub")
    else:
        print(f"Mode: Use local manifests")
    print(f"{'='*60}\n")

    for module in modules:
        generator = HelmChartGenerator(
            module_name=module['name'],
            module_config=module,
            manifests_dir=args.manifests_dir,
            output_dir=args.output_dir
        )
        generator.generate(download=args.download)
        print()

    print(f"{'='*60}")
    print(f"✅ Chart generation complete!")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
