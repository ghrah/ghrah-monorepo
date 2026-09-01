"""ghrah namespace package.

This file uses pkgutil-style namespace packages to allow multiple
packages to share the 'ghrah' namespace. Both ghrah-core and ghrah-subject
(and any future ghrah-* packages) can coexist under the same 'ghrah' top-level package.

See: https://packaging.python.org/en/latest/guides/packaging-namespace-packages/
"""
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
