import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

// Fixed-height data label: one line, truncated, with the full value as its tooltip.
const badgeVariants = cva(
  "inline-block h-5 max-w-full min-w-0 shrink-0 truncate rounded-sm border border-transparent px-1.5 align-middle text-xs leading-[1.125rem] font-medium",
  {
    variants: {
      variant: {
        default: "bg-signal-soft text-signal-deep",
        secondary: "bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  title,
  children,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span
      data-slot="badge"
      data-variant={variant}
      title={title ?? (typeof children === "string" ? children : undefined)}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    >
      {children}
    </span>
  )
}

export { Badge, badgeVariants }
