# -*- coding: utf-8 -*-
"""Put the payment/PHP snippet's include where the live site config sends .php to php-fpm.

Idempotent: a config that already includes it is left alone. The snippet
(deploy/nginx-yourcast-php.conf) serves the payment webhooks from the admin
process and answers 404 to any other .php: PHP 7.4 on the server is open to
PHP2Shell (2026-10), so no request goes to php-fpm.
"""
from __future__ import annotations

import re
import sys

MARKER = "include /etc/nginx/snippets/yourcast-php.conf;"
PHP_BLOCK = re.compile(
    r"\n(\s*)location ~ \\\.php\$ \{\n\s*include snippets/fastcgi-php\.conf;\n"
    r"\s*fastcgi_pass unix:/run/php/php[0-9.]+-fpm\.sock;\n\s*\}")


def ensure(path: str) -> bool:
    text = open(path, encoding="utf-8").read()
    updated, count = PHP_BLOCK.subn("\n\\1" + MARKER, text)
    if count == 0:
        if MARKER in text:
            print("nginx php include already present")
            return False
        raise SystemExit("did not find the php location or the include in %s" % path)
    open(path, "w", encoding="utf-8").write(updated)
    print("replaced %d php location(s) with the snippet include in %s" % (count, path))
    return True


if __name__ == "__main__":
    ensure(sys.argv[1] if len(sys.argv) > 1 else "/etc/nginx/sites-enabled/yourcast")
