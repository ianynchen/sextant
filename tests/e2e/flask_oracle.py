"""Flask's own answer to "what does this project serve?", printed as JSON.

Imports the corpus app and reads the REAL `app.url_map` (werkzeug's rule table), with no
registration logic of its own. Run with the FIXTURE's interpreter, never Sextant's; nothing here
may come from Sextant.

    <fixture>/.venv/bin/python flask_oracle.py <fixture root> [module:attribute]
"""

import json
import sys
from pathlib import Path
from typing import Any


def routes_of(app: Any) -> list[dict[str, Any]]:
    return [
        {
            "methods": sorted(rule.methods or ()),
            "path": rule.rule,
            "endpoint": rule.endpoint,
            "handler": app.view_functions[rule.endpoint].__qualname__,
            "handler_module": app.view_functions[rule.endpoint].__module__,
        }
        for rule in app.url_map.iter_rules()
    ]


def main(argv: list[str]) -> None:
    sys.path.insert(0, str(Path(argv[1]).resolve()))
    module, _, attribute = (argv[2] if len(argv) > 2 else "app.main:app").partition(":")
    app = getattr(__import__(module, fromlist=[attribute]), attribute)
    print(json.dumps(routes_of(app), indent=2))


if __name__ == "__main__":
    main(sys.argv)
