import { signalToBgColor } from "@/lib/constants";
import clsx from "clsx";

interface SignalBadgeProps {
  signal: string | null | undefined;
  className?: string;
}

export default function SignalBadge({ signal, className }: SignalBadgeProps) {
  if (!signal) return <span className="text-slate-400 text-xs">—</span>;

  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold whitespace-nowrap",
        signalToBgColor(signal),
        className
      )}
    >
      {signal}
    </span>
  );
}
