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
import { isBackendReachable } from '@/services/backend-api';
import { downloadOllamaModel, getOllamaStatus, OllamaDownloadProgress, OllamaStatus, startOllamaServer } from '@/services/ollama-api';
import { AgentModelConfig, ModelProvider } from '@/services/types';

// The repo a visitor without a local backend would need to clone. This is
// this deployment's own fork/origin - override via VITE_REPO_URL if you fork it again.
const REPO_URL = import.meta.env.VITE_REPO_URL || 'https://github.com/Amin-Debabeche/ai-hedge-fund';

type PreflightPhase =
  | 'checking-backend'
  | 'backend-unreachable'
  | 'checking-ollama'
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
  phase: 'checking-backend',
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
 * Before a run starts, this gates the run on two things in sequence:
 *
 * 1. Is this app's own backend reachable at all? Every model provider - local
 *    or cloud - is proxied through it, so if it's not running (e.g. someone
 *    opened a deployed link without ever setting up the backend on their own
 *    machine), nothing will work. Walks them through cloning and running it,
 *    and quietly re-checks in the background until it comes up.
 * 2. If the run needs an Ollama model, is Ollama itself installed, running,
 *    and does it have that model downloaded? If not, offers to auto-provision
 *    (start the server + pull the model) instead of failing mid-run.
 *
 * Render `dialog` somewhere in the tree and call `ensureReady(agentModels)`
 * before kicking off a run.
 */
export function useRunPreflight() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<PreflightState>(IDLE_STATE);
  const resolverRef = useRef<((ready: boolean) => void) | null>(null);
  const neededModelsRef = useRef<string[]>([]);

  const finish = useCallback((ready: boolean) => {
    setOpen(false);
    resolverRef.current?.(ready);
    resolverRef.current = null;
  }, []);

  const evaluateOllamaStatus = useCallback((status: OllamaStatus) => {
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

  const checkOllama = useCallback(async () => {
    try {
      const status = await getOllamaStatus();
      evaluateOllamaStatus(status);
    } catch {
      // The backend we just confirmed was up is now unreachable again.
      setState(prev => ({ ...prev, phase: 'backend-unreachable' }));
    }
  }, [evaluateOllamaStatus]);

  const checkBackend = useCallback(async () => {
    const reachable = await isBackendReachable();
    if (!reachable) {
      setState(prev => ({ ...prev, phase: 'backend-unreachable' }));
      return;
    }

    // Backend's up. If this run doesn't need an Ollama model, nothing left to check.
    if (neededModelsRef.current.length === 0) {
      finish(true);
      return;
    }

    setState(prev => ({ ...prev, phase: 'checking-ollama' }));
    await checkOllama();
  }, [checkOllama, finish]);

  // While waiting on the user to install/start something outside the app
  // (backend or Ollama itself), quietly re-check in the background so the
  // dialog advances on its own the moment it's ready - no manual retry needed.
  useEffect(() => {
    if (!open) return;
    if (state.phase !== 'backend-unreachable' && state.phase !== 'not-installed') return;

    const recheck = state.phase === 'backend-unreachable' ? checkBackend : checkOllama;
    const interval = setInterval(recheck, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [open, state.phase, checkBackend, checkOllama]);

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
    neededModelsRef.current = Array.from(
      new Set(
        agentModels
          .filter(m => m.model_provider === ModelProvider.OLLAMA && m.model_name)
          .map(m => m.model_name as string)
      )
    );

    return new Promise<boolean>(resolve => {
      resolverRef.current = resolve;
      setState({ ...IDLE_STATE, phase: 'checking-backend' });
      setOpen(true);
      checkBackend();
    });
  }, [checkBackend]);

  const dialog = (
    <Dialog open={open} onOpenChange={openState => { if (!openState) finish(false); }}>
      <DialogContent className="sm:max-w-md">
        {(state.phase === 'checking-backend' || state.phase === 'checking-ollama') && (
          <div className="flex items-center gap-3 py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {state.phase === 'checking-backend' ? 'Checking backend connection...' : 'Checking local Ollama setup...'}
            </span>
          </div>
        )}

        {state.phase === 'backend-unreachable' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Server className="h-5 w-5 text-amber-500" />
                Backend Not Running
              </DialogTitle>
              <DialogDescription>
                This app needs its backend running on your own machine to actually run agents -
                it's not a typical hosted web app. If you don't have it set up yet:
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <CopyableCommand command={`git clone ${REPO_URL}.git`} />
              <CopyableCommand command="cd ai-hedge-fund && poetry install" />
              <CopyableCommand command="cd app && poetry run uvicorn app.backend.main:app --reload" />
            </div>
            <p className="text-xs text-muted-foreground">
              Requires{' '}
              <a href="https://www.python.org/downloads/" target="_blank" rel="noopener noreferrer" className="underline">
                Python 3.11+
              </a>{' '}
              and{' '}
              <a href="https://python-poetry.org/docs/#installation" target="_blank" rel="noopener noreferrer" className="underline">
                Poetry
              </a>{' '}
              installed. Already have it cloned? Just run the last command from the project's <code>app</code> folder.
            </p>
            <p className="text-xs text-muted-foreground">
              Checking automatically every few seconds - this dialog will continue on its own once the backend is up.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => finish(false)}>Cancel</Button>
              <Button onClick={checkBackend}>Check Again</Button>
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
              <Button onClick={checkOllama}>Check Again</Button>
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
