const REVISED_PLAN_STATUS = 'Revised Plan from user feedback';
const REVISED_REPLAN_STATUS = 'Revised Replan from user feedback';

const INITIAL_PLAN_STATUSES = new Set([
  'Created Initial Plan',
  'Created Initial Replan',
]);

const FINAL_PLAN_STATUSES = new Set([
  'Reviewed Plan',
  'Reviewed Replan',
  REVISED_PLAN_STATUS,
  REVISED_REPLAN_STATUS,
]);

const TASK_PATTERNS = [
  /^#+\s*\*{0,2}Task\s*\d+/i,
  /^\*{2}Task\s*\d+/i,
  /^Task\s*\d+\s*[:：]/i,
  /^\d+[.)]\s*Task/i,
];

export const normalizePlanStatus = (status?: string): string => {
  return status || '';
};

export const isInitialPlanStatus = (status?: string): boolean => {
  return INITIAL_PLAN_STATUSES.has(normalizePlanStatus(status));
};

export const isFinalPlanStatus = (status?: string): boolean => {
  return FINAL_PLAN_STATUSES.has(normalizePlanStatus(status));
};

export const isPlanStatus = (status?: string): boolean => {
  return isInitialPlanStatus(status) || isFinalPlanStatus(status);
};

export const getInitialPlanStatus = (isReplan: boolean): string => {
  return isReplan ? 'Created Initial Replan' : 'Created Initial Plan';
};

export const getFinalPlanStatus = (isReplan: boolean): string => {
  return isReplan ? 'Reviewed Replan' : 'Reviewed Plan';
};

export const getRevisedPlanStatus = (isReplan: boolean): string => {
  return isReplan ? REVISED_REPLAN_STATUS : REVISED_PLAN_STATUS;
};

export const parseTasksFromPlanText = (text: string): string[] => {
  if (!text) return [];

  const tasks: string[] = [];
  let currentTask = '';
  let inTask = false;

  for (const line of text.split('\n')) {
    const trimmedLine = line.trim();
    if (!trimmedLine) continue;

    const isTaskLine = TASK_PATTERNS.some((pattern) => pattern.test(trimmedLine));

    if (isTaskLine) {
      if (currentTask) {
        tasks.push(currentTask.trim());
      }
      currentTask = trimmedLine;
      inTask = true;
    } else if (inTask) {
      if (
        /^---/.test(trimmedLine) ||
        /^#+\s*(?:\*\*)?\s*(?:Strategic Evaluation|Evaluation|Analysis|Conclusion)/i.test(trimmedLine)
      ) {
        break;
      }
      currentTask += '\n   ' + trimmedLine;
    }
  }

  if (currentTask) {
    tasks.push(currentTask.trim());
  }

  return tasks;
};

export const formatPlanTextForDisplay = (text?: string): string => {
  if (!text) return '';
  const parsedTasks = parseTasksFromPlanText(text);
  return parsedTasks.length > 0 ? parsedTasks.join('\n') : text;
};

export const formatPlanTasksForDisplay = (tasks?: string[]): string => {
  if (!tasks || tasks.length === 0) return '';
  return tasks.join('\n');
};
