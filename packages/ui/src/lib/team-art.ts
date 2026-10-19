const HUES = [8, 28, 52, 140, 164, 188, 210, 232, 256, 278, 300, 324, 346];

export type TeamArt = {
  light: string;
  dark: string;
  ink: string;
  angle: number;
  dots: { x: number; y: number; r: number }[];
};

function seeded(id: string) {
  let state = 2166136261;
  for (const char of id) {
    state = Math.imul(state ^ char.charCodeAt(0), 16777619);
  }
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = Math.imul(state ^ (state >>> 15), state | 1);
    mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

const cache = new Map<string, TeamArt>();

export function teamArt(id: string): TeamArt {
  const known = cache.get(id);
  if (known) {
    return known;
  }
  const next = seeded(id);
  const base = (HUES[Math.floor(next() * HUES.length)] ?? 0) + (next() - 0.5) * 16;
  const partner = base + (next() < 0.5 ? -1 : 1) * (24 + next() * 36);
  const angle = Math.floor(next() * 8) * 45 + 22.5;
  const spacing = 2 + next() * 1.2;
  const lattice = (next() * 30 + 30) * (Math.PI / 180);
  const reach = 0.55 + next() * 0.35;
  const direction = (angle * Math.PI) / 180;
  const along = { x: Math.cos(direction), y: Math.sin(direction) };
  const dots: TeamArt["dots"] = [];
  for (let u = -12; u <= 12; u += 1) {
    for (let v = -12; v <= 12; v += 1) {
      const x = 12 + spacing * (u * Math.cos(lattice) - v * Math.sin(lattice));
      const y = 12 + spacing * (u * Math.sin(lattice) + v * Math.cos(lattice));
      if (x < -1 || x > 25 || y < -1 || y > 25) {
        continue;
      }
      const t = ((x - 12) * along.x + (y - 12) * along.y) / 17 + 0.5;
      const r = (spacing / 2) * Math.max(0, (t - (1 - reach)) / reach) ** 1.4 * (0.85 + next() * 0.3);
      if (r > 0.12) {
        dots.push({ x: Number(x.toFixed(2)), y: Number(y.toFixed(2)), r: Number(r.toFixed(2)) });
      }
    }
  }
  const made = {
    light: `oklch(0.86 0.1 ${base.toFixed(0)})`,
    dark: `oklch(0.5 0.17 ${partner.toFixed(0)})`,
    ink: `oklch(0.96 0.04 ${base.toFixed(0)})`,
    angle,
    dots,
  };
  cache.set(id, made);
  return made;
}
