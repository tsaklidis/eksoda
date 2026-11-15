"""Registered receipt sources.

Adding a source (see the `add-provider` skill): a package under providers/ with
urls/parser/sanitize modules and a `provider` in its __init__, an entry below, a
doc in docs/providers/, sanitized fixtures with meta files, and tests. No model,
pipeline or API change is needed.
"""

from apps.receipts.providers import aade_fhm, entersoft, impact
from apps.receipts.providers.registry import ProviderRegistry

registry = ProviderRegistry([impact.provider, entersoft.provider, aade_fhm.provider])
