import clsx from "clsx";

interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export default function Card({ title, children, className }: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4",
        className
      )}
    >
      {title && (
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}
