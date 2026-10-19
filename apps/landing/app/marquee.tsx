import { cn } from "@relay/ui/lib/utils";
import { CSV_MARK } from "./fragments";

export type Engine = { name: string; logo?: string };

export function LogoMarquee({ engines }: { engines: Engine[] }) {
  return (
    <div className="group relative flex w-full overflow-hidden py-4 mask-[linear-gradient(to_right,transparent,black_15%,black_85%,transparent)] motion-reduce:mask-none">
      <ul className="flex w-max animate-marquee items-center gap-20 pl-20 group-hover:[animation-play-state:paused] motion-reduce:w-full motion-reduce:animate-none motion-reduce:flex-wrap motion-reduce:justify-center motion-reduce:gap-x-12 motion-reduce:gap-y-6 motion-reduce:pl-0">
        {[...engines, ...engines].map((engine, index) => (
          <li key={index} aria-hidden={index >= engines.length}
            className="flex items-center gap-3 motion-reduce:[&[aria-hidden=true]]:hidden opacity-60 grayscale transition-[opacity,filter] duration-300 hover:opacity-100 hover:grayscale-0 motion-reduce:transition-none">
            {engine.logo
              ? <img src={engine.logo} alt="" className="size-8 object-contain" />
              : <span className={cn(CSV_MARK, "size-8")} />}
            <span className="text-xl font-medium tracking-tight whitespace-nowrap text-ink/80">{engine.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
