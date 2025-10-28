# Chart Generator Templates

This directory contains template files used by `chart_generator.py` to generate Helm charts.

## Template Files

### `_helpers.tpl`
Helm template helpers for generated charts. Contains standard Helm helper definitions.

**Placeholders:**
- `{module_name}` - Replaced with the module name (e.g., `istio`, `keda`)

### `custom-resource.yaml`
Template for the custom resource manifest in generated charts.

**Placeholders:**
- `{api_version}` - CR apiVersion (e.g., `operator.kyma-project.io/v1alpha2`)
- `{kind}` - CR kind (e.g., `Istio`, `Keda`)
- `{name}` - Default CR name (e.g., `default`)
- `{spec_section}` - CR spec section (generated dynamically)

### `helmignore.txt`
Standard `.helmignore` file for generated charts. No placeholders.

## Customization

You can modify these templates to change the structure of generated charts:

1. **Edit template files** - Change the base structure
2. **Add placeholders** - Use `{placeholder_name}` format
3. **Update Python code** - Add `.replace()` calls in `chart_generator.py`

## Template Syntax

- **Placeholders**: `{variable_name}` - Simple string replacement
- **Helm syntax**: `{{ .Values.foo }}` - Preserved as-is in output
- **Comments**: Standard YAML/Helm comments

## Example

To add a new annotation to all generated charts:

1. Edit `_helpers.tpl`:
   ```yaml
   {{- define "{module_name}.labels" -}}
   custom.annotation: my-value
   ...
   ```

2. Regenerate charts:
   ```bash
   python3 chart_generator.py --download
   ```
