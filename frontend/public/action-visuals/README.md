# Action illustrations

Seven original corporate industrial PNG illustrations supplied by Marcos in
`frontend/public/BSS_TimeCollection_action_illustrations.zip`. Each deployed PNG
is an unchanged, byte-for-byte copy from that archive: 720 × 720 pixels, RGBA.

Stable visual keys: `end-work`, `break`, `factory`, `medical`, `personal`,
`legal`, `no-work`. Admin Actions/Sub-actions and terminal cards load these local
files using `.png`; no external image service is required. The frontend
Dockerfile copies this directory into the production image. CSS `object-fit:
contain` preserves proportions and transparency over the existing light cards.

`FACTORY_EXIT` uses `factory`; other existing Action/Sub-action assignments,
including optional empty illustrations, are preserved.
