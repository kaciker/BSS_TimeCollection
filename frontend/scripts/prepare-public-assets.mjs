import { cp, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const frontend = dirname(dirname(fileURLToPath(import.meta.url)));
const source = join(frontend, "img");
const target = join(frontend, "public", "img");
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true, force: true });
