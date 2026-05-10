import katex from "katex";
import clsx from "clsx";

interface MathProps {
  formula: string;
  className?: string;
}

function renderLatex(formula: string, displayMode: boolean): string {
  return katex.renderToString(formula, {
    throwOnError: false,
    displayMode,
    output: "html",
    strict: "ignore",
  });
}

export function MathBlock({ formula, className }: MathProps) {
  const html = renderLatex(formula, true);
  return (
    <div
      className={clsx(
        "mt-1 overflow-x-auto rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2 text-slate-800 dark:text-slate-200",
        className,
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export function MathInline({ formula, className }: MathProps) {
  const html = renderLatex(formula, false);
  return (
    <span
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default MathBlock;
