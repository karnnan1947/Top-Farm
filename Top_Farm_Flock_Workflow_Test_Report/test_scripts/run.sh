#!/usr/bin/env bash
# usage: run.sh data <phase>     -- pipes data/common.py + data/<phase>.py into the Odoo 20 shell
#        run.sh shots <steps>    -- runs browser/<steps>.js with Playwright (Odoo served on port 8021)
#        run.sh serve            -- serves the test database on port 8021 for the browser phases
set -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ODOO=/c/pycharmproject/odoo20/odoo
DB=${TF_DB:-topfarm20_flock}
ADDONS="C:\pycharmproject\odoo20\enterprise-20.0,C:\pycharmproject\odoo20\odoo\addons,C:\pycharmproject\odoo20\Top-Farm\top_farm_addons"
case "$1" in
  data)
    cd "$ODOO" && cat "$HERE/data/common.py" "$HERE/data/$2.py" | TF_PHASE="$2" ../.venv20/Scripts/python.exe odoo-bin shell \
      -c odoo.conf -d "$DB" --addons-path="$ADDONS" --no-http --log-level=warn 2>&1 \
      | grep -vE "^\s*$|DeprecationWarning|warnings.warn|invalid addons directory"
    ;;
  shots)
    cd "$HERE/browser" && NODE_PATH="${TF_NODE_MODULES:?set TF_NODE_MODULES to a folder with docx and playwright-core}" \
      node run_steps.js "$2.js" "${3:-admin}" "${4:-admin}"
    ;;
  serve)
    cd "$ODOO" && ../.venv20/Scripts/python.exe odoo-bin -c odoo.conf -d "$DB" --db-filter="^$DB\$" \
      --addons-path="$ADDONS" --http-port=8021 --log-level=warn
    ;;
  *) echo "usage: run.sh data <phase> | shots <steps> | serve"; exit 2 ;;
esac
