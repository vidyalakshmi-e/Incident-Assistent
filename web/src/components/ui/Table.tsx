import type { ReactNode } from "react";

export interface Col<T> {
  key: string;
  head: ReactNode;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  width?: string;
}

/** Hairline data table: one rule between rows, condensed annotation heads, tabular numerals. */
export function Table<T>({
  cols,
  rows,
  rowKey,
  empty = "No rows.",
  dense = false,
  highlight,
}: {
  cols: Col<T>[];
  rows: T[];
  rowKey: (r: T, i: number) => string;
  empty?: ReactNode;
  dense?: boolean;
  highlight?: (r: T) => boolean;
}) {
  if (!rows.length) return <p className="text-[14px] text-ink-3">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="num w-full border-collapse text-left text-[13.5px]">
        <thead>
          <tr className="border-b border-line-2">
            {cols.map((c) => (
              <th
                key={c.key}
                scope="col"
                style={c.width ? { width: c.width } : undefined}
                className={`annot px-2.5 pb-2 font-semibold whitespace-nowrap text-ink-3 first:pl-0 last:pr-0 ${c.align === "right" ? "text-right" : ""}`}
              >
                {c.head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={rowKey(r, i)} className={`border-b border-line align-top ${highlight?.(r) ? "bg-cobalt-soft/60" : ""}`}>
              {cols.map((c) => (
                <td
                  key={c.key}
                  className={`px-2.5 text-ink first:pl-0 last:pr-0 ${dense ? "py-1.5" : "py-2"} ${c.align === "right" ? "text-right" : ""}`}
                >
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
