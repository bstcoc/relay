import type { SVGProps } from "react";

export function RelayMark({ size = 24, title, ...props }: SVGProps<SVGSVGElement> & { size?: number; title?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      <path d="M5 3H14.5Q18.5 3 15.5 6L6 15.5Q3 18.5 3 14.5V5A2 2 0 0 1 5 3Z" />
      <path d="M19 21H9.5Q5.5 21 8.5 18L18 8.5Q21 5.5 21 9.5V19A2 2 0 0 1 19 21Z" />
    </svg>
  );
}
