import { teamArt } from "@relay/ui/lib/team-art"

export function TeamArt({ id, className }: { id: string; className?: string }) {
  const key = `team-${id}`
  const art = teamArt(id)
  return (
    <span className={className} aria-hidden="true">
      <svg viewBox="0 0 24 24" className="block size-full">
        <defs>
          <linearGradient id={`${key}g`} gradientTransform={`rotate(${art.angle} 0.5 0.5)`}>
            <stop offset="0" stopColor={art.light} />
            <stop offset="1" stopColor={art.dark} />
          </linearGradient>
          <mask id={`${key}m`}>
            <rect width="24" height="24" fill="white" />
            <path d="M0 24L24 0" stroke="black" strokeWidth="1.2" />
          </mask>
        </defs>
        <g mask={`url(#${key}m)`}>
          <rect width="24" height="24" fill={`url(#${key}g)`} />
          <g fill={art.ink} fillOpacity="0.55">
            {art.dots.map((dot) => <circle key={`${dot.x} ${dot.y}`} cx={dot.x} cy={dot.y} r={dot.r} />)}
          </g>
        </g>
      </svg>
    </span>
  )
}
