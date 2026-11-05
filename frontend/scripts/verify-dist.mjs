import { access, readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

const root = new URL("../dist/", import.meta.url).pathname;
const required = ["index.html", "img/logobig.png", "img/hutchinson_logo.png", "img/rfid-card.svg", "action-visuals/README.md"];
for (const file of required) {
  try { await access(join(root, file)); }
  catch { throw new Error(`Frontend build is missing required asset: ${file}`); }
}
const html = await readFile(join(root, "index.html"), "utf8");
if (!html.includes("/assets/") || html.includes("/src/main.tsx")) throw new Error("Frontend build output is not a production Vite bundle");
const visualFiles = (await readdir(join(root, "action-visuals"))).filter(file => file.endsWith(".png"));
const catalogue = await readFile(new URL("../src/actionVisuals.ts", import.meta.url), "utf8");
const keys = [...catalogue.matchAll(/"key":\s*"([a-z0-9-]+)"/g)].map(match => match[1]);
const missingVisuals = keys.filter(key => !visualFiles.includes(`${key}.png`));
if (missingVisuals.length) throw new Error(`Frontend build is missing action illustrations: ${missingVisuals.join(", ")}`);
console.log(`Verified production bundle, ${required.length} required assets, and ${visualFiles.length} action illustrations.`);
