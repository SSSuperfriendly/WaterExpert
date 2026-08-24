"use client";

import * as React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/waterexpert/ui-states";

export interface ColumnDef {
  key: string;
  header: React.ReactNode;
  render?: (row: Record<string, unknown>, index: number) => React.ReactNode;
}

/**
 * Generic data table for dynamic backend rows. Supports horizontal scrolling
 * for wide (Chinese) content and long text without layout overflow.
 */
export function DataTable({
  columns,
  rows,
  rowKey,
  emptyHint,
}: {
  columns: ColumnDef[];
  rows: Record<string, unknown>[];
  rowKey?: (row: Record<string, unknown>, index: number) => string;
  emptyHint?: string;
}) {
  if (!rows || rows.length === 0) {
    return <EmptyState description={emptyHint} />;
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((col) => (
              <TableHead key={col.key} className="max-w-[280px]">
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={rowKey ? rowKey(row, i) : i}>
              {columns.map((col) => (
                <TableCell key={col.key} className="max-w-[280px]">
                  {col.render ? col.render(row, i) : String(row[col.key] ?? "")}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
