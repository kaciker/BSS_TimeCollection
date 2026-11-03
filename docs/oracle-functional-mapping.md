# Oracle functional mapping

Oracle structural values are configured on the BSS structure hierarchy, not on terminals:

`Terminal → ProjectLine.oracle_cell_code → Subworkshop.oracle_machine_code → Workshop.oracle_work_area_code`

Local structure codes and descriptions remain unchanged and separate. Oracle options are selected from the explicit HR-Path catalogue exposed by `/api/v1/admin/structure/oracle-catalogue`; backend validation enforces catalogue membership and parent relationships. Unverified values remain unmapped. No mappings are inferred by changing local strings.

Each new CELL `TimeEvent` freezes the resolved Person ID, PayrollTimeType, Oracle WORK_AREA/MACHINE/CELL, supplier event/direction, timestamp and request number. Later structure or Action edits do not rewrite that snapshot. PayrollTimeType, WORK_AREA, MACHINE and CELL are protected contract fields; generic `oracle_attributes` cannot replace them. Perimeter events stay `LOCAL_ONLY`. Oracle device ID remains stored for compatibility but is optional and is not sent in the current Time Event payload.

The currently verified catalogue data in code is deliberately limited to the values supplied and corroborated for this change: PayrollTimeTypes `Public Holiday ES`, `Workshop Entry ES`, `Project Entry ES`, `Non-productive time ES`, `Break ES`; WORK_AREA `439`; MACHINE `4391`, `4392`, `4393` under 439; CELL `54Q` under 4391. Extend this list only from the authoritative HR-Path workbook. The workbook was not present in the repository or available deployment filesystem during this implementation.

The live T0007 local path is Workshop `439 / Nave 1`, Subworkshop `439.1 / P24 / D34`, ProjectLine `P24 GVTD / P24 GVT Derecha`. HR-Path CELL `54Q` is described as `G.V. D34` under MACHINE `4391`; the supplied evidence does not establish that this ProjectLine is that exact functional cell, so its CELL mapping stays NULL. The live T0010 local ProjectLine is `P24 GVD D / P24 GVD Derecha`; no authoritative evidence supplied here maps it to a CELL, so that CELL also stays NULL. In particular, the reported `54T` association is unverified and is not included in the catalogue.

For one selected event, follow [the one-event send procedure](oracle-one-event-send.md). Automatic delivery stays disabled until a separate operational go-live decision.
