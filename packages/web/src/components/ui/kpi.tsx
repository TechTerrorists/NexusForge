import { clsx } from "clsx";

interface KpiProps {
  label: string;
  value: string | number;
  unit?: string;
  delta?: string;
  deltaDirection?: "up" | "down" | "neutral";
  className?: string;
}

export function Kpi({ label, value, unit, delta, deltaDirection = "neutral", className }: KpiProps) {
  return (
    <div className={clsx("kpi", className)}>
      <div className="label">{label}</div>
      <div className="val">
        {value}
        {unit && <span className="u">{unit}</span>}
      </div>
      {delta && (
        <div className={clsx("delta", deltaDirection === "up" && "up", deltaDirection === "down" && "down")}>
          {deltaDirection === "up" && "↑ "}
          {deltaDirection === "down" && "↓ "}
          {delta}
        </div>
      )}
    </div>
  );
}
