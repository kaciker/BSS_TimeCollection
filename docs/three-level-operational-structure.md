# Three-level operational structure

Status: **Approved functional requirement**
Date: 2026-10-13

## Decision

T&A must use exactly three business levels for the operational structure:

1. **Workshop**
2. **Subworkshop**
3. **Project / Line**

This hierarchy is managed inside T&A and is then assigned to terminals. It must be configurable for any plant/site and must not be hardcoded to the Arganda example.

Example:

| Workshop | Subworkshop | Project / Line |
|---|---|---|
| `428 - Extrusión TP - Juntas Estáticas` | `4282 - TP2-TP3-TP4-TP5` | `TP4 - Operarios TP4` |

## Functional model

### Workshop

Fields:

| Field | Requirement |
|---|---|
| Internal ID | Stable DB identifier |
| Code | Business/Oracle code |
| Description | Display description |
| Active | Active/inactive state |

Workshop code must be unique at Workshop level.

### Subworkshop

Fields:

| Field | Requirement |
|---|---|
| Internal ID | Stable DB identifier |
| Workshop ID | Required parent |
| Code | Business/Oracle code |
| Description | Display description |
| Active | Active/inactive state |

A Subworkshop always belongs to one Workshop. Its code only needs to be unique inside its parent Workshop.

### Project / Line

Fields:

| Field | Requirement |
|---|---|
| Internal ID | Stable DB identifier |
| Subworkshop ID | Required parent |
| Code | Business/Oracle code |
| Description | Display description |
| Active | Active/inactive state |

A Project / Line always belongs to one Subworkshop. Its code only needs to be unique inside its parent Subworkshop. Project/Line codes are **not globally unique**; values such as `1`, `2`, `53B`, `511`, etc. may legitimately exist under different branches.

The business identity of a leaf is therefore the complete path:

`Workshop + Subworkshop + Project/Line`

## Administration UI

Add a dedicated **Structure** area in Admin.

The UI must be table-first and compact. Avoid explanatory paragraphs when a table, label, status or tooltip is sufficient.

Primary view:

| Workshop | Subworkshop | Project / Line | Description | Status | Actions |
|---|---|---|---|---|---|
| 428 | 4281 | TP1 | Operarios TP1 | Active | Edit |
| 428 | 4282 | TP2 | Operarios TP2 | Active | Edit |
| 428 | 4282 | TP3 | Operarios TP3 | Active | Edit |
| 428 | 4282 | TP4 | Operarios TP4 | Active | Edit |
| 428 | 4282 | TP5 | Operarios TP5 | Active | Edit |

Required operations:

- Create/edit/activate/deactivate Workshop.
- Create/edit/activate/deactivate Subworkshop under a Workshop.
- Create/edit/activate/deactivate Project / Line under a Subworkshop.
- Filter by Workshop, Subworkshop, status and free-text search.
- Prevent invalid parent/child relationships.
- Do not physically delete records already referenced by terminals or historical events; use inactive state.

The Arganda Excel structure is a reference dataset only. The application must allow administrators to build a different hierarchy manually for another plant/site.

## Terminal configuration

The existing free-form **Oracle terminal context JSON** must no longer be exposed to administrators as the way to configure operational structure.

A terminal must select one valid active hierarchy path:

| Field | Example |
|---|---|
| Workshop | `428 - Extrusión TP - Juntas Estáticas` |
| Subworkshop | `4282 - TP2-TP3-TP4-TP5` |
| Project / Line | `TP4 - Operarios TP4` |

Selection behavior:

- Workshop selector lists active Workshops.
- Subworkshop selector only lists active children of the selected Workshop.
- Project / Line selector only lists active children of the selected Subworkshop.
- Changing a parent clears incompatible child selections.
- Backend validation must reject inconsistent combinations even if the UI is bypassed.
- Terminal list/table should show the assigned hierarchy compactly.

The existing `work_cell` concept used by exit policy is separate from this three-level structure and must continue to work.

## Event snapshot and auditability

Historical events must not depend on later edits of the master structure.

At event creation, store a snapshot containing at least:

- `workshop_code`
- `workshop_description`
- `subworkshop_code`
- `subworkshop_description`
- `project_line_code`
- `project_line_description`

Renaming or deactivating a structure record later must not alter an existing event snapshot.

Keep the current event/audit principle: local events remain the auditable system-of-record for what was captured at the terminal.

## Oracle / Fizz integration

The three-level structure is business context managed by T&A. The Oracle/Fizz adapter is responsible for translating that context into the final Oracle `timeEventAttributes` mapping once the Oracle implementation team confirms the exact attribute names/codes.

Do not expose raw Oracle attribute JSON in normal terminal administration for these three fields.

Do not hardcode provisional Oracle attribute names before the final Oracle mapping is confirmed.

Existing event fields such as terminal/device ID, reporter, event date/time and supplier device event remain unchanged.

## Data model direction

Expected normalized tables:

- `workshops`
- `subworkshops`
- `project_lines`

Terminals should reference the selected leaf (`project_line_id`) and derive/validate its Subworkshop and Workshop through the hierarchy. Avoid storing three independent foreign keys that could become inconsistent unless there is a demonstrated need.

Historical events keep denormalized snapshot values for auditability.

## Migration / compatibility

The implementation must preserve current terminal identity, provisioning, actions, exit policies, events and Oracle delivery history.

Current `terminal.oracle_attributes` may still contain unrelated technical/integration attributes. Migration must not silently discard unknown existing attributes. The three-level structure, however, becomes normalized and administered through the Structure model rather than free-form JSON.

Existing historical events must remain unchanged.

## UX direction

For this feature and future Admin work, prioritize:

1. Tables
2. Filters/search
3. Compact status indicators
4. Direct row actions
5. Short forms/dialogs
6. Tooltips/help only where needed

Avoid long descriptive text in normal operational screens.

## Acceptance criteria

Implementation is complete when:

- Exactly three business levels exist: Workshop -> Subworkshop -> Project / Line.
- Admin can build and maintain the hierarchy without editing JSON or source code.
- The same codes can safely exist in different valid parent branches.
- Terminal configuration uses cascading hierarchy selectors.
- Invalid hierarchy combinations are rejected server-side.
- A terminal event captures an immutable snapshot of the selected path.
- Current terminal provisioning, actions/sub-actions and exit-policy behavior remain functional.
- Current historical data and Oracle transmission history are preserved.
- Admin UI is table-oriented and does not introduce unnecessary explanatory text.
- Backend tests and frontend build/tests cover the new hierarchy and regression behavior.
