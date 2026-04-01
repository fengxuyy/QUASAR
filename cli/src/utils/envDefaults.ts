import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

export interface EnvVarDef {
    key: string;
    description: string;
    options?: string[];
    isSensitive?: boolean;
    defaultValue?: string;
}

export const ENV_VAR_DEFS: EnvVarDef[] = [
    { key: 'MODEL', description: 'Model name' },
    { key: 'MODEL_API_KEY', description: 'API key', isSensitive: true },
    { key: 'OPENAI_API_BASE', description: 'API base URL' },
    { key: 'ACCURACY', description: 'Accuracy mode', options: ['eco', 'standard', 'pro'], defaultValue: 'standard' },
    { key: 'GRANULARITY', description: 'Task breakdown', options: ['low', 'medium', 'high'], defaultValue: 'medium' },
    { key: 'CONTEXT_THRESHOLD', description: 'Context compression threshold', options: ['low', 'medium', 'high'], defaultValue: 'medium' },
    { key: 'ENABLE_RAG', description: 'Doc search', options: ['true', 'false'], defaultValue: 'true' },
    { key: 'PMG_MAPI_KEY', description: 'Materials Project key', isSensitive: true },
    { key: 'CHECK_INTERVAL', description: 'Check-in interval (min)' },
    { key: 'AUTO_IMPROVE_CYCLES', description: 'Automatic auto-improve follow-up runs', defaultValue: '0' },
    { key: 'NUM_CORES', description: 'CPU cores', defaultValue: 'Auto' },
    { key: 'STRATEGIST_MODEL', description: 'Strategist model' },
    { key: 'STRATEGIST_MODEL_API_KEY', description: 'Strategist API key', isSensitive: true },
    { key: 'STRATEGIST_API_BASE_URL', description: 'Strategist API base' },
    { key: 'OPERATOR_MODEL', description: 'Operator model' },
    { key: 'OPERATOR_MODEL_API_KEY', description: 'Operator API key', isSensitive: true },
    { key: 'OPERATOR_API_BASE_URL', description: 'Operator API base' },
    { key: 'EVALUATOR_MODEL', description: 'Evaluator model' },
    { key: 'EVALUATOR_MODEL_API_KEY', description: 'Evaluator API key', isSensitive: true },
    { key: 'EVALUATOR_API_BASE_URL', description: 'Evaluator API base' },
];

const PROJECT_WORKSPACE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../workspace');

export function resolveWorkspaceDir(): string {
    const candidates = [process.env.WORKSPACE_DIR, PROJECT_WORKSPACE_DIR, '/workspace'].filter(
        (dir): dir is string => Boolean(dir),
    );

    const existingDir = candidates.find(dir => fs.existsSync(dir));
    return existingDir || process.env.WORKSPACE_DIR || PROJECT_WORKSPACE_DIR;
}

export function applyDefaultEnv() {
    let checkpointSettings: Record<string, any> = {};
    let hasCheckpoint = false;
    
    try {
        const workspaceDir = resolveWorkspaceDir();
        const checkpointDbPath = path.join(workspaceDir, 'checkpoints.sqlite');
        const settingsPath = path.join(workspaceDir, 'checkpoint_settings.json');
        
        if (fs.existsSync(checkpointDbPath) && fs.existsSync(settingsPath)) {
            hasCheckpoint = true;
            const content = fs.readFileSync(settingsPath, 'utf-8');
            checkpointSettings = JSON.parse(content);
            
            if (!checkpointSettings.MODEL && checkpointSettings._usage_stats?.model_name) {
                checkpointSettings.MODEL = checkpointSettings._usage_stats.model_name;
            }
        }
    } catch (e) {
        // Silently ignore
    }

    for (const def of ENV_VAR_DEFS) {
        if (process.env[def.key] === undefined) {
            if (hasCheckpoint && checkpointSettings[def.key] !== undefined) {
                process.env[def.key] = checkpointSettings[def.key];
            } else if (def.defaultValue !== undefined) {
                process.env[def.key] = def.defaultValue;
            }
        }
    }
}
