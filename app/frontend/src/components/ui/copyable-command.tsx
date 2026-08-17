import { Check, Copy } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';

export function CopyableCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access denied - nothing we can do, the command is still visible to copy manually.
    }
  };

  return (
    <div className="flex items-center justify-between gap-2 bg-muted rounded-md px-3 py-2 font-mono text-xs">
      <code className="truncate">{command}</code>
      <Button variant="ghost" size="sm" onClick={copy} className="h-6 w-6 p-0 shrink-0">
        {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
      </Button>
    </div>
  );
}
