import clsx from "clsx";

interface PeaBadgeProps {
  eligible: boolean;
  pme?: boolean;
}

export default function PeaBadge({ eligible, pme = false }: PeaBadgeProps) {
  if (!eligible && !pme) {
    return null;
  }

  if (pme && eligible) {
    return (
      <span className="inline-flex items-center gap-1">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
          PEA
        </span>
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
          PME
        </span>
      </span>
    );
  }

  if (pme) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
        PEA-PME
      </span>
    );
  }

  return (
    <span
      className={clsx(
        "inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold",
        eligible
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
          : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-500 opacity-50"
      )}
    >
      PEA
    </span>
  );
}
