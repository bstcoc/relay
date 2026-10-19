"use client";

import { Button } from "@relay/ui/components/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@relay/ui/components/dialog";
import { Input } from "@relay/ui/components/input";
import { useState } from "react";
import { usePreferences } from "../../../preferences";
import { Field } from "../../../components/ui";

export function Confirm({ name, onConfirm, onClose }: { name: string; onConfirm: () => void; onClose: () => void }) {
  const { t } = usePreferences();
  const [typed, setTyped] = useState("");
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent showCloseButton={false} className="gap-4">
        <DialogHeader>
          <DialogTitle className="heading-3">{t.wizard.production}</DialogTitle>
          <DialogDescription>{t.wizard.productionBody}</DialogDescription>
        </DialogHeader>
        <Field label={<span className="wrap-anywhere text-foreground">{name}</span>}>
          <Input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t.form.cancel}</Button>
          <Button disabled={typed !== name} onClick={onConfirm}>{t.wizard.confirm}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
