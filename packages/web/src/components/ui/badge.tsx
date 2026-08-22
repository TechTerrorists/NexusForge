import { clsx } from "clsx";

type BadgeVariant = "blue" | "purple" | "emerald" | "amber" | "red" | "default";

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = "default", children, className }: BadgeProps) {
  return (
    <span className={clsx("badge", variant !== "default" && variant, className)}>
      {children}
    </span>
  );
}
