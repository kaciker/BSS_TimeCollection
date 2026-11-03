# Oracle Catalogue operations

Oracle HR-Path reference values are operational PostgreSQL data. They are not sourced from Python constants. BSS structure records store nullable references to catalogue codes; a CELL event freezes the selected PayrollTimeType, WORK_AREA, MACHINE, CELL, supplier event, and event context into its own snapshot.

## Admin changes

Use **Admin → Oracle Catalogue** to search the active and inactive records, add records at each hierarchy level, update descriptions/parent links, and deactivate values. A machine must have an active WORK_AREA parent and a cell must have an active MACHINE parent. Structure mapping controls show only catalogue values with the required active parent. PayrollTimeType is selected from the catalogue in Action administration.

Codes are immutable after creation. To replace a code, add the new record, reassign local mappings, then deactivate the old record. Existing event snapshots are not changed by catalogue edits.

## Import the complete HR-Path workbook

The workbook `HUT Attributes.xlsx` has four authoritative tabs: `Elements - Time Type`, `Lookups - Workshop`, `Lookups - Sub-workshop`, and `Lookups - Project`. Convert all enabled records into one canonical JSON document:

```json
{
  "work_areas": [{"code":"439","description":"Acabado TP","active":true,"source_reference":"HUT Attributes.xlsx / Lookups - Workshop"}],
  "machines": [{"code":"4391","description":"T439.1","work_area_code":"439","active":true,"source_reference":"HUT Attributes.xlsx / Lookups - Sub-workshop"}],
  "cells": [{"code":"54T","description":"G.V. P24","machine_code":"4391","active":true,"source_reference":"HUT Attributes.xlsx / Lookups - Project"}],
  "payroll_time_types": [{"code":"Workshop Entry ES","description":null,"active":true,"source_reference":"HUT Attributes.xlsx / Elements - Time Type"}]
}
```

Include every enabled row from all four tabs. Resolve parent codes from the workbook's explicit parent relationships; never derive codes from BSS local values. Validate the converted JSON locally, then POST it as an authenticated administrator to `/api/v1/admin/structure/oracle-catalogue/import` with `Content-Type: application/json`. The endpoint checks every machine/work-area and cell/machine relationship before its single transaction. It reports `added`, `updated`, `unchanged`, and `invalid` counts. A rejected import rolls back completely. Entries omitted from an import are retained; deactivation is explicit.

The complete workbook was not present in the deployment workspace at the time persistent catalogue support was implemented. The migration therefore seeds only the currently verified values needed to preserve T0010/T0007 and START_WORK. Import the complete workbook before treating the catalogue as complete.

Automatic Oracle delivery remains controlled by `ORACLE_ENABLED`; catalogue administration does not enable or transmit events.
