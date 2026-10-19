import { cn } from "@relay/ui/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "relative overflow-hidden rounded-md bg-tile after:absolute after:inset-0 after:animate-shimmer after:bg-linear-to-r after:from-transparent after:via-background/60 after:to-transparent motion-reduce:after:hidden",
        className
      )}
      {...props}
    />
  )
}

export { Skeleton }
