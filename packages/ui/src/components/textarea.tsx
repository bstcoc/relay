import * as React from "react"
import { cn } from "@relay/ui/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-2xl border border-input bg-field px-3.5 py-2 text-base transition-[color,border-color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-border-strong focus-visible:ring-2 focus-visible:ring-border-strong/30 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 md:text-sm dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
