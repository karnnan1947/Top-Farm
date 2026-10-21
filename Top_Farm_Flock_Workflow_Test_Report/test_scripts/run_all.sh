#!/usr/bin/env bash
# Full workflow test on a freshly installed database (see README.md): data phases and browser steps, in order.
# The test database must be installed and served on port 8021 (run.sh serve) before running this script.
# Browser steps run as the Farm Manager (admin) unless a login is given (the Farm Operator is created by p00).
set -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
STEPS=(
  "data p00_setup" "shots s00_setup"
  "data p01_purchase" "shots s01_purchase"
  "data p02_dispatch" "shots s02_dispatch"
  "data p03_manual_dispatch" "shots s03_manual_dispatch" "data p03b_manual_checks"
  "data p04_brooding" "shots s04_brooding" "shots s04b_mortality_operator operator operator123" "shots s04c_brooding_analytics"
  "shots s05_allocation"
  "data p06_rearing" "shots s06_rearing"
  "data p07_point_of_lay" "shots s07_point_of_lay"
  "data p07b_point_of_lay" "shots s07b_start_laying"
  "data p08_laying" "shots s08_laying"
  "data p08b_laying" "shots s08b_eggs"
  "data p09_sales" "shots s09_sales"
  "data p09b_invoices" "shots s09b_invoices"
  "data p10_verify" "shots s10_reports"
  "data p11_cage_reuse" "shots s11_cage_reuse"
  "data p11b_cage_reuse" "shots s11b_cage_reuse"
)
for step in "${STEPS[@]}"; do
  echo "=== $step"
  out=$(./run.sh $step 2>&1)
  status=$?
  echo "$out"
  if [ $status -ne 0 ] || grep -qE "Traceback|STEP FAILED" <<<"$out"; then
    echo "!!! stopped at: $step"
    exit 1
  fi
done
echo "=== all steps done"
