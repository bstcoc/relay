"use client";

import { Button } from "@relay/ui/components/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@relay/ui/components/dropdown-menu";
import { Ellipsis } from "lucide-react";

export type MenuItem = { label: string; onSelect: () => void; danger?: boolean; disabled?: boolean };

export function Menu({ label, items }: { label: string; items: MenuItem[] }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="outline" size="icon-sm" aria-label={label}
          className="justify-self-end rounded-full shadow-none data-[state=open]:bg-muted">
          <Ellipsis />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" aria-label={label} className="min-w-50 p-1">
        {items.map((item) => (
          <DropdownMenuItem key={item.label} disabled={item.disabled} variant={item.danger ? "destructive" : "default"}
            className="h-9 px-2" onSelect={item.onSelect}>
            {item.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
