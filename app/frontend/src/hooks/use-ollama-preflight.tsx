import { AlertTriangle, Download, Loader2, Server } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { CopyableCommand } from '@/components/ui/copyable-command';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { downloadOllamaModel, getOllamaStatus, OllamaDownloadProgress, OllamaStatus, startOllamaServer } from '@/services/ollama-api';
import { AgentModelConfig, ModelProvider } from '@/services/types';

type PreflightPhase =
  | 'checking'
  | 'backend-unreachable'
  | 'not-installed'
  | 'prompt'
  | 'provisioning'
  | 'error';

interface PreflightState {
  phase: PreflightPhase;
  modelsNeeded: string[];
  serverNeedsStart: boolean;
  progress: Record<string, OllamaDownloadProgress>;
  error: string | null;
}

const IDLE_STATE: PreflightState = {
  phase: 'checking',
  modelsNeeded: [],
  serverNeedsStart: false,
  progress: {},
  error: null,
};

const POLL_INTERVAL_MS = 3000;

function describeSetupNeeded(modelsNeeded: string[], serverNeedsStart: boolean): string {
  const needs: string[] = [];
  if (serverNeedsStart) {
    needs.push('start the local Ollama server');
  }
  if (modelsNeeded.length > 0) {
    needs.push(`download ${modelsNeeded.length > 1 ? 'models' : 'model'} ${modelsNeeded.join(', ')}`);
  }
  return `This run needs to ${needs.join(' and ')}. Set this up now and continue the run?`;
}

/**
 * Before a run starts, checks whether every Ollama model an agent needs is
 * actually downloaded and the local server is running. If not, prompts the
 * user to auto-provision (start the server + pull the model) instead of
 * letting the run silently fail. If the backend or Ollama itself isn't set
 * up on this machine at all, walks the user through getting it installed and
 * quietly re-checks in the background until it's ready. Render `dialog`
 * somewhere in the tree and call `ensureReady(agentModels)` before kicking
 * off a run.
 */
export function useOllamaPreflight() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<PreflightState>(IDLE_STATE);
  const resolverRef = useRef<((ready: boolean) => void) | null>(null);
  const neededModelsRef = useRef<string[]>([]);

  const finish = useCallback((ready: boolean) => {
    setOpen(false);
    resolverRef.current?.(ready);
    resolverRef.current = null;
  }, []);

  const evaluateStatus = useCallback((status: OllamaStatus) => {
    if (!status.installed) {
      setState(prev => ({ ...prev, phase: 'not-installed' }));
      return;
    }

    const modelsNeeded = neededModelsRef.current.filter(name => !status.available_models.includes(name));
    const serverNeedsStart = !status.running;

    if (modelsNeeded.length === 0 && !serverNeedsStart) {
      // Everything's already in place - don't bother the user.
      finish(true);
      return;
    }

    setState(prev => ({ ...prev, phase: 'prompt', modelsNeeded, serverNeedsStart }));
  }, [finish]);

  const checkStatus = useCallback(async () => {
    try {
      const status = await getOllamaStatus();
      evaluateStatus(status);
    } catch {
      // Can't even reach the backend - it's likely not running on this machine.
      setState(prev => ({ ...prev, phase: 'backend-unreachable' }));
    }
  }, [evaluateStatus]);

  // While waiting on the user to install/start something outside the app
  // (backend or Ollama itself), quietly re-check in the background so the
  // dialog advances on its own the moment it's ready - no manual retry needed.
  useEffect(() => {
    if (!open) return;
    if (state.phase !== 'backend-unreachable' && state.phase !== 'not-installed') return;

    const interval = setInterval(checkStatus, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [open, state.phase, checkStatus]);

  const provision = useCallback(async (modelsNeeded: string[], serverNeedsStart: boolean) => {
    setState(prev => ({ ...prev, phase: 'provisioning', error: null }));
    try {
      if (serverNeedsStart) {
        await startOllamaServer();
      }
      for (const modelName of modelsNeeded) {
        await downloadOllamaModel(modelName, progress => {
          setState(prev => ({ ...prev, progress: { ...prev.progress, [modelName]: progress } }));
        });
      }
      finish(true);
    } catch (error) {
      setState(prev => ({
        ...prev,
        phase: 'error',
        error: error instanceof Error ? error.message : 'Failed to set up Ollama',
      }));
    }
  }, [finish]);

  const ensureReady = useCallback((agentModels: AgentModelConfig[]): Promise<boolean> => {
    const neededModels = Array.from(
      new Set(
        agentModels
          .filter(m => m.model_provider === ModelProvider.OLLAMA && m.model_name)
          .map(m => m.model_name as string)
      )
    );

    // No Ollama models involved in this run - nothing to check, proceed immediately.
    if (neededModels.length === 0) {
      return Promise.resolve(true);
    }

    neededModelsRef.current = neededModels;

    return new Promise<boolean>(resolve => {
      resolverRef.current = resolve;
      setState({ ...IDLE_STATE, phase: 'checking' });
      setOpen(true);
      checkStatus();
    });
  }, [checkStatus]);

  const dialog = (
    <Dialog open={open} onOpenChange={openState => { if (!openState) finish(false); }}>
      <DialogContent className="sm:max-w-md">
        {state.phase === 'checking' && (
          <div className="flex items-center gap-3 py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Checking local Ollama setup...</span>
          </div>
        )}

        {state.phase === 'backend-unreachable' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Server className="h-5 w-5 text-amber-500" />
                Local Backend Not Running
              </DialogTitle>
              <DialogDescription>
                To use a local model, this app's backend needs to be running on your own machine -
                it's what talks to Ollama for you. From the project folder, run:
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <CopyableCommand command="poetry install" />
              <CopyableCommand command="cd app && poetry run uvicorn app.backend.main:app --reload" />
            </div>
            <p className="text-xs text-muted-foreground">
              Checking automatically every few seconds - this dialog will continue on its own once the backend is up.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => finish(false)}>Cancel</Button>
              <Button onClick={checkStatus}>Check Again</Button>
            </DialogFooter>
          </>
        )}

        {state.phase === 'not-installed' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-500" />
                Install Ollama
              </DialogTitle>
              <DialogDescription>
                This run needs a local model, which requires Ollama installed on this machine.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <CopyableCommand command="brew install ollama   # macOS" />
              <CopyableCommand command="curl -fsSL https://ollama.com/install.sh | sh   # Linux" />
              <p className="text-xs text-muted-foreground">
                Windows: download the installer from{' '}
                <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" className="underline">
                  ollama.com
                </a>.
              </p>
            </div>
            <p className="text-xs text-muted-foreground">
              Checking automatically every few seconds - this dialog will continue on its own once Ollama is installed.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => finish(false)}>Cancel</Button>
              <Button onClick={checkStatus}>Check Again</Button>
            </DialogFooter>
          </>
        )}

        {(state.phase === 'prompt' || state.phase === 'error') && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Download className="h-5 w-5 text-primary" />
                Local Model Setup Needed
              </DialogTitle>
              <DialogDescription>
                {describeSetupNeeded(state.modelsNeeded, state.serverNeedsStart)}
              </DialogDescription>
            </DialogHeader>
            {state.error && (
              <p className="text-sm text-red-500">{state.error}</p>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => finish(false)}>Cancel</Button>
              <Button onClick={() => provision(state.modelsNeeded, state.serverNeedsStart)}>
                {state.phase === 'error' ? 'Retry' : 'Download & Run'}
              </Button>
            </DialogFooter>
          </>
        )}

        {state.phase === 'provisioning' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
                Setting Up Ollama
              </DialogTitle>
              <DialogDescription>
                {state.serverNeedsStart && Object.keys(state.progress).length === 0
                  ? 'Starting the local server...'
                  : 'Downloading the model needed for this run...'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              {state.modelsNeeded.map(modelName => {
                const progress = state.progress[modelName];
                return (
                  <div key={modelName} className="space-y-1">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{modelName}</span>
                      <span>{progress?.percentage ? `${progress.percentage.toFixed(0)}%` : '...'}</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2">
                      <div
                        className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${progress?.percentage || 0}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );

  return { ensureReady, dialog };
}
