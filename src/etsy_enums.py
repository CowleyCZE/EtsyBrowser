"""Etsy Open API v3 and CSV Enums and Constants.

Centralized source of truth for Etsy taxonomy enums, listing types,
and policies (e.g. AI transparency, who_made, when_made).
"""

from enum import Enum


class WhoMade(str, Enum):
    """Allowed values for 'who_made' in Etsy Open API v3 and CSV.
    
    Etsy Policy:
    - i_did: Seller created/designed the product (including AI with original human prompt/direction)
    - collective: A member of seller's shop/collective created it
    - someone_else: Another company or production partner created it
    """
    I_DID = "i_did"
    COLLECTIVE = "collective"
    SOMEONE_ELSE = "someone_else"


class WhenMade(str, Enum):
    """Allowed values for 'when_made' in Etsy Open API v3."""
    MADE_TO_ORDER = "made_to_order"
    YEARS_2020_2026 = "2020_2026"
    YEARS_2010_2019 = "2010_2019"
    YEARS_2007_2009 = "2007_2009"
    BEFORE_2007 = "before_2007"
    YEARS_2000_2006 = "2000_2006"
    DECADE_1990S = "1990s"
    DECADE_1980S = "1980s"
    DECADE_1970S = "1970s"
    DECADE_1960S = "1960s"
    DECADE_1950S = "1950s"
    DECADE_1940S = "1940s"
    DECADE_1930S = "1930s"
    DECADE_1920S = "1920s"
    DECADE_1910S = "1910s"
    DECADE_1900S = "1900s"
    CENTURY_1800S = "1800s"
    CENTURY_1700S = "1700s"
    BEFORE_1700 = "before_1700"


class ListingType(str, Enum):
    """Allowed values for 'type' (digital vs physical)."""
    PHYSICAL = "physical"
    DOWNLOAD = "download"
    BOTH = "both"


class ListingState(str, Enum):
    """Allowed values for listing state."""
    ACTIVE = "active"
    DRAFT = "draft"


# Standard AI disclosure note required by Etsy transparency policy in description
AI_DISCLOSURE_TEXT = (
    "\n\n---\nCreated with generative AI assistance and curated, directed, and edited by the shop owner."
)
