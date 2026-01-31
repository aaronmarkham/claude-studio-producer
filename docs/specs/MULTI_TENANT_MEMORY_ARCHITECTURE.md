---
layout: default
title: Multi-Tenant Memory Architecture & Security Model
---
# Multi-Tenant Memory Architecture & Security Model

## Overview

This document defines the complete namespace hierarchy, access control model, and security policies for Claude Studio Producer's multi-tenant memory system.

## Implementation Status

**Implemented** - The multi-tenant memory system is fully implemented with:

| Component | Status | Location |
|-----------|--------|----------|
| Namespace Builder | ✅ Done | `core/memory/namespace.py` |
| Backend Interface | ✅ Done | `core/memory/backends/base.py` |
| Local Storage | ✅ Done | `core/memory/backends/local.py` |
| AgentCore Backend | ✅ Placeholder | `core/memory/backends/agentcore.py` |
| Multi-Tenant Manager | ✅ Done | `core/memory/multi_tenant_manager.py` |
| CLI Commands | ✅ Done | `cli/memory.py` |
| Unit Tests | ✅ Done | `tests/unit/test_multi_tenant_memory.py` |

### CLI Commands

```bash
# View memory statistics
claude-studio memory stats

# List learnings by provider
claude-studio memory list luma

# Search learnings
claude-studio memory search "camera motion" -p luma

# Add a learning
claude-studio memory add luma "Use concrete nouns for subjects"

# Export/import learnings
claude-studio memory export -o learnings.json
claude-studio memory import learnings.json

# Set user preferences
claude-studio memory set-pref default_provider luma

# View namespace tree
claude-studio memory tree
```

### Python Usage

```python
from core.memory import get_memory_manager, NamespaceLevel

# Get global manager (auto-detects local vs hosted mode)
manager = get_memory_manager()
ctx = manager.get_context()

# Store a learning
await manager.store_provider_learning(
    provider="luma",
    learning={"pattern": "Use concrete nouns", "effectiveness": 0.85},
    level=NamespaceLevel.USER,
    ctx=ctx,
)

# Retrieve learnings (merges from all levels by priority)
learnings = await manager.get_provider_learnings("luma", ctx)

# Search learnings
results = await manager.search_learnings("camera motion", provider="luma", ctx=ctx)

# Set preferences
await manager.set_preferences({"default_provider": "luma"}, ctx)
```

## Namespace Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              NAMESPACE TREE                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  /                                                                               │
│  ├── platform/                           # PLATFORM SCOPE (cross-tenant)        │
│  │   ├── learnings/                                                             │
│  │   │   ├── global/                     # Universal truths                     │
│  │   │   │   └── {recordId}              # "AI video can't render text"        │
│  │   │   └── provider/                                                          │
│  │   │       ├── luma/                   # Luma-specific platform knowledge    │
│  │   │       │   └── {recordId}          # "Luma can't do VFX transforms"      │
│  │   │       ├── runway/                                                        │
│  │   │       │   └── {recordId}                                                 │
│  │   │       └── {providerId}/                                                  │
│  │   │           └── {recordId}                                                 │
│  │   └── config/                         # Platform configuration              │
│  │       ├── providers                   # Available providers                  │
│  │       ├── tiers                       # Tier definitions                     │
│  │       └── limits                      # Platform limits                      │
│  │                                                                              │
│  ├── org/                                # ORGANIZATION SCOPE                   │
│  │   └── {orgId}/                                                               │
│  │       ├── learnings/                                                         │
│  │       │   ├── global/                 # Org-wide learnings                  │
│  │       │   │   └── {recordId}          # "Our brand uses warm tones"         │
│  │       │   └── provider/                                                      │
│  │       │       └── {providerId}/       # Org's provider experience           │
│  │       │           └── {recordId}                                             │
│  │       ├── config/                     # Org configuration                   │
│  │       │   ├── preferences             # Org-wide defaults                   │
│  │       │   ├── brand_assets            # Shared brand assets                 │
│  │       │   └── quality_threshold       # Org quality standards               │
│  │       ├── actor/                      # USER SCOPE                          │
│  │       │   └── {actorId}/                                                     │
│  │       │       ├── learnings/                                                 │
│  │       │       │   ├── global/         # User's proven patterns             │
│  │       │       │   │   └── {recordId}                                        │
│  │       │       │   └── provider/                                              │
│  │       │       │       └── {providerId}/                                      │
│  │       │       │           └── {recordId}                                     │
│  │       │       ├── preferences/        # User preferences                    │
│  │       │       │   └── {recordId}                                             │
│  │       │       ├── sessions/           # SESSION SCOPE                       │
│  │       │       │   └── {sessionId}/                                           │
│  │       │       │       ├── learnings/  # Session experiments                 │
│  │       │       │       │   └── {recordId}                                     │
│  │       │       │       └── context/    # Session working memory              │
│  │       │       │           └── {recordId}                                     │
│  │       │       └── runs/               # Run history                         │
│  │       │           └── {runId}/                                               │
│  │       │               ├── summary                                            │
│  │       │               ├── scenes/                                            │
│  │       │               └── assets/                                            │
│  │       └── shared/                     # Org shared resources                │
│  │           ├── templates/              # Shared prompt templates             │
│  │           └── assets/                 # Shared media assets                 │
│  │                                                                              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Namespace Patterns

| Pattern | Example | Scope | Typical Use |
|---------|---------|-------|-------------|
| `/platform/learnings/global` | - | All tenants | Universal AI video truths |
| `/platform/learnings/provider/{providerId}` | `/platform/learnings/provider/luma` | All tenants | Provider capabilities/limits |
| `/org/{orgId}/learnings/global` | `/org/acme/learnings/global` | Org members | Org-specific patterns |
| `/org/{orgId}/learnings/provider/{providerId}` | `/org/acme/learnings/provider/luma` | Org members | Org's provider experience |
| `/org/{orgId}/actor/{actorId}/learnings/global` | `/org/acme/actor/alice/learnings/global` | Single user | User's proven patterns |
| `/org/{orgId}/actor/{actorId}/sessions/{sessionId}` | `/org/acme/actor/alice/sessions/20260111` | Single session | Experimental learnings |
| `/org/{orgId}/actor/{actorId}/preferences` | `/org/acme/actor/alice/preferences` | Single user | User settings |

## Access Control Model

### Roles

| Role | Description | Typical Assignment |
|------|-------------|-------------------|
| `platform_admin` | Full platform access | Platform operators |
| `platform_curator` | Can promote to platform learnings | ML/Content team |
| `org_admin` | Full org access | Org administrators |
| `org_curator` | Can promote to org learnings | Team leads |
| `org_member` | Standard org access | Regular users |
| `org_viewer` | Read-only org access | Stakeholders |

### Permission Matrix

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    PERMISSION MATRIX                                         │
├───────────────────────────────┬──────────┬──────────┬──────────┬──────────┬────────┬────────┤
│ Namespace                     │ platform │ platform │ org      │ org      │ org    │ org    │
│                               │ _admin   │ _curator │ _admin   │ _curator │ _member│ _viewer│
├───────────────────────────────┼──────────┼──────────┼──────────┼──────────┼────────┼────────┤
│ /platform/learnings/*         │ RWD      │ RW       │ R        │ R        │ R      │ R      │
│ /platform/config/*            │ RWD      │ R        │ R        │ R        │ R      │ R      │
├───────────────────────────────┼──────────┼──────────┼──────────┼──────────┼────────┼────────┤
│ /org/{orgId}/learnings/*      │ RWD      │ RW       │ RWD      │ RW       │ R      │ R      │
│ /org/{orgId}/config/*         │ RWD      │ R        │ RWD      │ R        │ R      │ R      │
│ /org/{orgId}/shared/*         │ RWD      │ RW       │ RWD      │ RW       │ RW     │ R      │
├───────────────────────────────┼──────────┼──────────┼──────────┼──────────┼────────┼────────┤
│ /org/{orgId}/actor/{self}/*   │ RWD      │ RWD      │ RWD      │ RWD      │ RWD    │ R      │
│ /org/{orgId}/actor/{other}/*  │ RWD      │ R        │ RWD      │ R        │ -      │ -      │
├───────────────────────────────┼──────────┼──────────┼──────────┼──────────┼────────┼────────┤
│ Legend: R=Read, W=Write, D=Delete, -=No Access                                              │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

## IAM Policies (AWS AgentCore)

### 1. Platform Admin Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PlatformAdminFullAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateMemoryRecord",
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:UpdateMemoryRecord",
        "bedrock-agentcore:DeleteMemoryRecord",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": "*"
        }
      }
    }
  ]
}
```

### 2. Platform Curator Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PlatformCuratorReadAll",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": "*"
        }
      }
    },
    {
      "Sid": "PlatformCuratorWritePlatformLearnings",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateMemoryRecord",
        "bedrock-agentcore:UpdateMemoryRecord"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": "/platform/learnings/*"
        }
      }
    }
  ]
}
```

### 3. Org Admin Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OrgAdminReadPlatform",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": "/platform/*"
        }
      }
    },
    {
      "Sid": "OrgAdminFullOrgAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateMemoryRecord",
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:UpdateMemoryRecord",
        "bedrock-agentcore:DeleteMemoryRecord",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringEquals": {
          "bedrock-agentcore:namespace": "/org/${aws:PrincipalTag/org_id}/*"
        }
      }
    }
  ]
}
```

### 4. Org Member Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OrgMemberReadPlatform",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": "/platform/*"
        }
      }
    },
    {
      "Sid": "OrgMemberReadOrgLearnings",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": [
            "/org/${aws:PrincipalTag/org_id}/learnings/*",
            "/org/${aws:PrincipalTag/org_id}/config/*"
          ]
        }
      }
    },
    {
      "Sid": "OrgMemberReadWriteOrgShared",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateMemoryRecord",
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:UpdateMemoryRecord",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": "/org/${aws:PrincipalTag/org_id}/shared/*"
        }
      }
    },
    {
      "Sid": "OrgMemberFullOwnAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateMemoryRecord",
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:UpdateMemoryRecord",
        "bedrock-agentcore:DeleteMemoryRecord",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": "/org/${aws:PrincipalTag/org_id}/actor/${aws:PrincipalTag/actor_id}/*"
        }
      }
    }
  ]
}
```

### 5. Org Viewer Policy (Read-Only)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OrgViewerReadOnly",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:RetrieveMemoryRecords",
        "bedrock-agentcore:ListMemoryRecords"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/${MemoryId}",
      "Condition": {
        "StringLike": {
          "bedrock-agentcore:namespace": [
            "/platform/*",
            "/org/${aws:PrincipalTag/org_id}/*"
          ]
        }
      }
    }
  ]
}
```

## Promotion Flow & Rules

### Promotion Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              PROMOTION FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   SESSION LEARNING                                                               │
│   /org/{o}/actor/{a}/sessions/{s}/learnings/{id}                                │
│        │                                                                         │
│        │ [Actor promotes OR auto-promote after 3 validations]                   │
│        ▼                                                                         │
│   USER LEARNING                                                                  │
│   /org/{o}/actor/{a}/learnings/provider/{p}/{id}                                │
│        │                                                                         │
│        │ [Org curator promotes OR system detects 3+ users with same pattern]   │
│        ▼                                                                         │
│   ORG LEARNING                                                                   │
│   /org/{o}/learnings/provider/{p}/{id}                                          │
│        │                                                                         │
│        │ [Platform curator promotes OR system detects 3+ orgs with same]       │
│        ▼                                                                         │
│   PLATFORM LEARNING                                                              │
│   /platform/learnings/provider/{p}/{id}                                         │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Auto-Promotion Rules

```python
AUTO_PROMOTION_RULES = {
    "session_to_user": {
        "min_validations": 3,        # Learning helped 3+ times
        "min_confidence": 0.7,       # 70%+ success rate
        "min_age_hours": 24,         # At least 24 hours old
        "requires_approval": False,  # Auto-promote
    },
    "user_to_org": {
        "min_users": 3,              # 3+ users have same learning
        "min_confidence": 0.8,       # 80%+ success rate across users
        "similarity_threshold": 0.9, # Semantic similarity of learnings
        "requires_approval": True,   # Org curator must approve
    },
    "org_to_platform": {
        "min_orgs": 3,               # 3+ orgs have same learning
        "min_confidence": 0.9,       # 90%+ success rate across orgs
        "similarity_threshold": 0.95,# Very high semantic similarity
        "requires_approval": True,   # Platform curator must approve
    },
}
```

### Promotion Record Schema

```python
@dataclass
class PromotionRecord:
    """Tracks the promotion history of a learning"""
    original_id: str
    original_namespace: str
    promoted_id: str
    promoted_namespace: str
    promoted_at: datetime
    promoted_by: str              # Actor ID or "system"
    promotion_reason: str         # "manual", "auto_validation", "cross_user_pattern"
    evidence: List[str]           # Supporting record IDs
    confidence_at_promotion: float
    validations_at_promotion: int
```

## Security Considerations

### 1. Namespace Isolation

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ISOLATION BOUNDARIES                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  HARD BOUNDARY: Organization                                                     │
│  ├─ Org A cannot read/write Org B's namespaces                                  │
│  ├─ Enforced by IAM policy with org_id tag                                      │
│  └─ No cross-org queries possible without platform role                         │
│                                                                                  │
│  SOFT BOUNDARY: Actor within Org                                                 │
│  ├─ Actor A can read Org-level learnings                                        │
│  ├─ Actor A cannot read Actor B's personal data                                 │
│  ├─ Org Admin can read all actors for support/debugging                         │
│  └─ Enforced by IAM policy with actor_id tag                                    │
│                                                                                  │
│  NO BOUNDARY: Platform                                                           │
│  ├─ Platform learnings readable by all authenticated users                      │
│  ├─ Platform learnings writable only by curators/admins                         │
│  └─ This is intentional - platform knowledge benefits everyone                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2. Data Classification

| Data Type | Classification | Retention | Encryption |
|-----------|---------------|-----------|------------|
| Platform learnings | Public (to tenants) | Indefinite | At-rest + Transit |
| Org learnings | Org-confidential | Org policy | At-rest + Transit |
| User learnings | User-private | User policy | At-rest + Transit |
| Session data | Ephemeral | 30 days default | At-rest + Transit |
| Run artifacts | User-private | 90 days default | At-rest + Transit |
| Preferences | User-private | Account lifetime | At-rest + Transit |

### 3. Audit Trail

All memory operations are logged:

```python
@dataclass
class MemoryAuditEvent:
    timestamp: datetime
    event_type: str          # "create", "read", "update", "delete", "promote"
    actor_id: str
    org_id: str
    namespace: str
    record_id: Optional[str]
    query: Optional[str]     # For retrieve operations
    result_count: Optional[int]
    source_ip: str
    user_agent: str
    
# Audit events go to CloudWatch Logs with 1-year retention
# Sensitive queries (preferences, personal data) flagged for review
```

### 4. Rate Limiting

```python
RATE_LIMITS = {
    "retrieve": {
        "per_minute": 100,
        "per_hour": 1000,
        "burst": 20,
    },
    "create": {
        "per_minute": 30,
        "per_hour": 300,
        "burst": 10,
    },
    "promote": {
        "per_hour": 10,      # Promotions are expensive/impactful
        "per_day": 50,
    },
}
```

### 5. Content Validation

```python
CONTENT_VALIDATION = {
    "max_record_size_bytes": 65536,      # 64KB per record
    "max_text_content_chars": 10000,     # 10K chars for text search
    "forbidden_patterns": [
        r"\b\d{3}-\d{2}-\d{4}\b",        # SSN
        r"\b\d{16}\b",                    # Credit card
        r"password\s*[:=]\s*\S+",        # Passwords
    ],
    "pii_detection": True,               # AgentCore default
    "sanitize_on_promote": True,         # Extra scrub when promoting
}
```

## Retrieval Strategy

### Priority-Based Multi-Namespace Query

```python
class LearningRetriever:
    """
    Retrieves learnings from multiple namespaces with priority ordering.
    """
    
    NAMESPACE_PRIORITY = [
        # Highest priority: Platform-curated knowledge
        ("platform_global", "/platform/learnings/global", 1.0),
        ("platform_provider", "/platform/learnings/provider/{provider}", 0.95),
        
        # High priority: Org-level knowledge
        ("org_global", "/org/{org}/learnings/global", 0.85),
        ("org_provider", "/org/{org}/learnings/provider/{provider}", 0.80),
        
        # Medium priority: User's proven patterns
        ("user_global", "/org/{org}/actor/{actor}/learnings/global", 0.70),
        ("user_provider", "/org/{org}/actor/{actor}/learnings/provider/{provider}", 0.65),
        
        # Lowest priority: Session experiments
        ("session", "/org/{org}/actor/{actor}/sessions/{session}/learnings", 0.50),
    ]
    
    async def retrieve(
        self,
        query: str,
        provider: str,
        context: RetrievalContext,
        top_k: int = 20,
    ) -> List[ScoredLearning]:
        """
        Retrieve learnings from all applicable namespaces.
        
        Scores are adjusted by namespace priority to ensure platform
        learnings rank higher than user experiments.
        """
        all_results = []
        
        for name, pattern, priority_weight in self.NAMESPACE_PRIORITY:
            namespace = self._build_namespace(pattern, context)
            
            try:
                results = await self.memory.retrieve_memories(
                    namespace=namespace,
                    query=query,
                    top_k=top_k,
                )
                
                for record in results:
                    # Adjust score by namespace priority
                    adjusted_score = record.score * priority_weight
                    all_results.append(ScoredLearning(
                        record=record,
                        raw_score=record.score,
                        adjusted_score=adjusted_score,
                        source_namespace=name,
                    ))
            except NamespaceNotFoundError:
                continue  # Namespace doesn't exist yet
            except AccessDeniedError:
                continue  # User doesn't have access
        
        # Sort by adjusted score, dedupe similar content
        all_results.sort(key=lambda x: x.adjusted_score, reverse=True)
        deduped = self._dedupe_similar(all_results, similarity_threshold=0.9)
        
        return deduped[:top_k]
```

## Local Development Mapping

For local development, the same namespace structure is used with JSON files:

```
artifacts/memory/
├── platform/
│   └── learnings/
│       ├── global.json
│       └── provider/
│           ├── luma.json
│           └── runway.json
├── org/
│   └── {orgId}/
│       ├── learnings/
│       │   ├── global.json
│       │   └── provider/
│       │       └── {providerId}.json
│       └── actor/
│           └── {actorId}/
│               ├── learnings/
│               │   └── ...
│               ├── preferences.json
│               └── sessions/
│                   └── {sessionId}.json
```

This allows:
- Same namespace logic in local and production
- Easy migration to AgentCore
- File-based inspection during development
- Git-trackable platform learnings (seed data)
