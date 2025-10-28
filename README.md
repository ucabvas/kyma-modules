# Kyma Module Helm Chart Generator

Automated tool for generating Helm charts from Kyma module manifests.

## Overview

This tool converts Kyma module manifests (manager + custom resource) into standardized Helm charts by:

1. **Splitting CRDs** - Extracts CustomResourceDefinitions to `crds/` folder (installed first by Helm)
2. **Converting Custom Resources** - Transforms CRs into templated values with `{{ .Values }}` substitutions
3. **Creating Standard Structure** - Generates complete Helm chart with Chart.yaml, templates, values.yaml
4. **Tracking Versions** - Records upstream module versions in Chart.yaml annotations

## Features

- ✅ Single-command chart generation for all modules
- ✅ Automatic CRD extraction and organization
- ✅ Custom resource templating with Helm values
- ✅ Version tracking from upstream releases
- ✅ Standard Helm helpers and best practices
- ✅ Module-specific configuration via `modules.yaml`

## Prerequisites

- Python 3.8+
- PyYAML

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Generate All Charts (from local manifests)

```bash
python3 chart_generator.py
```

### Download Latest Manifests and Generate

```bash
python3 chart_generator.py --download
```

This will:
1. Fetch the latest release from each module's GitHub repository
2. Download the manager and CR manifest files
3. Generate Helm charts from the downloaded manifests

### Generate Specific Module

```bash
# From local manifests
python3 chart_generator.py --module istio

# Download latest and generate
python3 chart_generator.py --module istio --download
```

### Custom Configuration

```bash
python3 chart_generator.py \
  --config modules.yaml \
  --manifests-dir . \
  --output-dir charts \
  --download
```

## Configuration

All modules are defined in `modules.yaml`:

```yaml
modules:
  - name: istio
    repo: kyma-project/istio
    manager_file: istio-manager.yaml
    cr_file: istio-default-cr.yaml
    description: "Istio service mesh integration for Kyma"
    chart_version: "1.0.0"
```

### Fields

- `name` - Chart name (required)
- `repo` - GitHub repository path (required)
- `manager_file` - Manager/operator manifest filename (required)
- `cr_file` - Custom resource manifest filename (optional)
- `description` - Chart description
- `chart_version` - Helm chart version (your versioning)

## Generated Chart Structure

```
charts/
  <module-name>/
    Chart.yaml              # Chart metadata + upstream version
    .helmignore
    crds/                   # CustomResourceDefinitions
      *.yaml
    templates/
      manager.yaml          # Deployment, RBAC, Services
      custom-resource.yaml  # Templated CR (if exists)
      _helpers.tpl          # Helm helpers
    values.yaml             # Configuration values
```

## Chart.yaml Annotations

Each generated chart includes tracking annotations:

```yaml
annotations:
  upstream-repo: kyma-project/istio
  upstream-version: 1.22.1
  generated-date: 2025-10-27T22:54:51Z
```

## Using Generated Charts

### Install with Helm

```bash
helm install istio charts/istio -n kyma-system --create-namespace
```

### Customize Values

```bash
helm install istio charts/istio \
  --set manager.enabled=true \
  --set customResource.enabled=true \
  -n kyma-system
```

### Override Custom Resource Spec

```yaml
# my-values.yaml
customResource:
  enabled: true
  spec:
    # Your custom configuration
```

```bash
helm install istio charts/istio -f my-values.yaml -n kyma-system
```

## Version Tracking

The generator extracts upstream versions from:
1. Container image tags in manager manifests
2. Stored in `Chart.yaml` as `appVersion` and `annotations.upstream-version`

Use these annotations for CI/CD to detect new upstream releases.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Update Charts

on:
  schedule:
    - cron: '0 0 * * *'  # Daily
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Download and generate charts
        run: python3 chart_generator.py --download

      - name: Validate charts
        run: |
          for chart in charts/*; do
            helm lint $chart
          done

      - name: Create PR if changes
        # Use peter-evans/create-pull-request or similar
```

## Updating Manifests

### Manual Update

1. Download new manifests to `manifests/` directory
2. Update version in `modules.yaml` if needed
3. Run generator: `python3 chart_generator.py`

### Automated Update Script

```bash
#!/bin/bash
# update_manifests.sh

for module in istio keda serverless telemetry nats eventing api-gateway; do
  repo="kyma-project/${module}"
  [ "$module" = "serverless" ] && repo="kyma-project/serverless"
  [ "$module" = "api-gateway" ] && repo="kyma-project/api-gateway"

  # Download latest from GitHub releases
  # Update modules.yaml with new versions
done

python3 chart_generator.py
```

## Development

### Adding a New Module

1. Add manifest files to `manifests/`
2. Add module entry to `modules.yaml`
3. Run generator

### Customizing Chart Generation

Edit `chart_generator.py` to:
- Modify template generation logic
- Add custom value substitutions
- Change chart structure
- Add validation rules

## Troubleshooting

### Missing Manager File

```
⚠️  Manager file not found: xxx-manager.yaml
```

Ensure the manifest file exists in the manifests directory and matches the name in `modules.yaml`.

### Missing CR File

If CR file is optional, set `cr_file: null` in `modules.yaml`. The generator will skip custom resource template generation.

### YAML Parsing Errors

Ensure manifest files are valid YAML with proper document separators (`---`).

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test with all modules
5. Submit pull request

## License

See LICENSE file for details.

## Maintainers

- Kyma Project Team
- Community Contributors

## References

- [Kyma Project](https://kyma-project.io)
- [Helm Documentation](https://helm.sh/docs/)
- [Kubernetes API Reference](https://kubernetes.io/docs/reference/)
