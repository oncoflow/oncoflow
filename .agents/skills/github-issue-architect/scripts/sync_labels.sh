#!/usr/bin/env bash
# Synchronizes the DataSyntis GitHub label taxonomy from `.github/labels.yml`
# Requires: `gh` CLI authenticated (`gh auth status`) and `python3` + PyYAML/regex.

set -euo pipefail

REPO="${1:-oncoflow/oncoflow}"
LABELS_FILE=".github/labels.yml"

if [[ ! -f "$LABELS_FILE" ]]; then
  echo "Error: $LABELS_FILE not found." >&2
  exit 1
fi

echo "Syncing labels to repository: $REPO from $LABELS_FILE..."

python3 - "$LABELS_FILE" "$REPO" <<'PYEOF'
import re
import subprocess
import sys

labels_file = sys.argv[1]
repo = sys.argv[2]

with open(labels_file, encoding="utf-8") as f:
    content = f.read()

pattern = re.compile(
    r'- name:\s*"([^"]+)"\s*\n\s*color:\s*"([^"]+)"\s*\n\s*description:\s*"([^"]*)"',
    re.MULTILINE,
)

matches = pattern.findall(content)
for name, color, description in matches:
    print(f"  -> Upserting label: {name} (#{color})")
    subprocess.run(
        [
            "gh",
            "label",
            "create",
            name,
            "--repo",
            repo,
            "--color",
            color,
            "--description",
            description,
            "--force",
        ],
        check=True,
    )

print(f"Successfully synchronized {len(matches)} labels.")
PYEOF
