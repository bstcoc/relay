import * as React from "react"
import { cn } from "@relay/ui/lib/utils"

function ButtonGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      role="group"
      data-slot="button-group"
      className={cn(
        "flex w-fit items-stretch gap-1 [&>*]:focus-visible:relative [&>*]:focus-visible:z-10",
        className
      )}
      {...props}
    />
  )
}

export { ButtonGroup }
