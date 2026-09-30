from enum import Enum


class SourceType(str, Enum):
    OFFICIAL = "OFFICIAL"
    MEDIA = "MEDIA"
    COMMUNITY = "COMMUNITY"


class EvidenceType(str, Enum):
    SUPPORTING = "SUPPORTING"
    COUNTER = "COUNTER"


class OpportunityCategory(str, Enum):
    CONTENT = "CONTENT"
    BUSINESS = "BUSINESS"
    ARCHITECTURE = "ARCHITECTURE"
    CAREER = "CAREER"
