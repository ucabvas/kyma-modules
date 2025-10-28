#!/bin/bash
set -e

echo "Testing chart generator with templates..."

# Clean up any existing test output
rm -rf test-charts

# Generate a single chart
python3 chart_generator.py --module nats --download --output-dir test-charts

# Verify the chart was created
if [ ! -d "test-charts/nats" ]; then
    echo "❌ Chart directory not created"
    exit 1
fi

# Verify all expected files exist
for file in Chart.yaml values.yaml .helmignore templates/_helpers.tpl templates/manager.yaml crds; do
    if [ ! -e "test-charts/nats/$file" ]; then
        echo "❌ Missing: $file"
        exit 1
    fi
done

# Lint the chart
helm lint test-charts/nats

echo "✅ All tests passed!"

# Cleanup
rm -rf test-charts
