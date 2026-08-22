import { clsx } from "clsx";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "ghost";
  size?: "default" | "sm";
  children: React.ReactNode;
}

export function Button({ variant = "default", size = "default", className, children, ...props }: ButtonProps) {
  return (
    <button
      className={clsx(
        "btn",
        variant === "primary" && "primary",
        variant === "ghost" && "ghost",
        size === "sm" && "sm",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
