import { clsx } from "clsx";

interface PanelProps {
  children: React.ReactNode;
  className?: string;
}

export function Panel({ children, className }: PanelProps) {
  return <div className={clsx("panel", className)}>{children}</div>;
}

export function PanelHead({ children, className }: PanelProps) {
  return <div className={clsx("panel-head", className)}>{children}</div>;
}

export function PanelBody({ children, className, flush }: PanelProps & { flush?: boolean }) {
  return <div className={clsx("panel-body", flush && "flush", className)}>{children}</div>;
}
