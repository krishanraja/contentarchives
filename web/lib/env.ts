// Every secret by symbolic name, read at request time. A missing one stops
// loudly: a gate whose code is "" would let anyone in.
export function need(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`missing environment variable ${name}`);
  return v;
}
export const imageSource = () =>
  (process.env.IMAGE_SOURCE || "drive") as "drive" | "fixture";
