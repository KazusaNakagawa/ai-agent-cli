// Every run writes its own timestamped file under results/, so a re-run never
// overwrites the run it is being compared against.
import { mkdirSync, writeFileSync } from 'node:fs';

const dir = new URL('./results/', import.meta.url).pathname;

export function saveResult(name, data) {
  mkdirSync(dir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const path = `${dir}${name}-${stamp}.json`;
  writeFileSync(path, JSON.stringify(data, null, 2));
  console.log(`saved      : ${path}`);
  return path;
}
