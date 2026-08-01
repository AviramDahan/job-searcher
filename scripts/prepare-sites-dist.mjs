import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";

const target = join("dist", ".openai", "hosting.json");

mkdirSync(dirname(target), { recursive: true });
copyFileSync(join(".openai", "hosting.json"), target);

