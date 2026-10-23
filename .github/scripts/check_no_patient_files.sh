#!/usr/bin/env bash
# Refuse tout document susceptible de contenir des données patients (PDF, bureautique,
# bases locales...) en dehors des emplacements autorisés. Le dépôt est public :
# n'y versionner que des référentiels publics ou des documents entièrement fictifs.
#
# Usage : .github/scripts/check_no_patient_files.sh [fichiers...]
#   sans argument : vérifie tous les fichiers suivis par git (CI)
#   avec arguments : vérifie les fichiers donnés (hook pre-commit)
set -euo pipefail

# Extensions surveillées (insensible à la casse)
WATCHED='\.(pdf|docx?|odt|rtf|xlsx?|ods|csv|hl7|dcm|sqlite3?|db|bbox)$'

# Emplacements autorisés (expressions régulières étendues)
ALLOWED=(
  '^application/ressources/documents/'   # référentiels publics (TNCD...)
  '\.sample\.(pdf|docx)$'                # documents explicitement fictifs
  '^application/tests/fixtures/'         # jeux de test fictifs
  '^experiment/rcp_parser/test_final(_2)?\.pdf$'  # gabarits de fiche vides
  '^experiment/test_precedent/test\.pdf$'         # gabarit de fiche vide
  '^experiment/RAG/chroma/chroma\.sqlite3$'       # base Chroma vide
)

if [ "$#" -gt 0 ]; then
  files=$(printf '%s\n' "$@")
else
  files=$(git ls-files)
fi

status=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  echo "$f" | grep -qiE "$WATCHED" || continue
  allowed=false
  for pattern in "${ALLOWED[@]}"; do
    if echo "$f" | grep -qE "$pattern"; then allowed=true; break; fi
  done
  if [ "$allowed" = false ]; then
    echo "::error file=$f::Fichier potentiellement patient refusé : $f (dépôt public, voir AGENTS.md)"
    status=1
  fi
done <<< "$files"

exit $status
