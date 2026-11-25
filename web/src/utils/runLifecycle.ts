export interface RunLifecycleState {
  revision: number;
  completionSuppressed: boolean;
}

export const createRunLifecycleState = (): RunLifecycleState => ({
  revision: 0,
  completionSuppressed: false,
});

export const beginTrackedRun = (state: RunLifecycleState): number => {
  state.revision += 1;
  state.completionSuppressed = false;
  return state.revision;
};

export const suppressRunCompletion = (state: RunLifecycleState): number => {
  state.revision += 1;
  state.completionSuppressed = true;
  return state.revision;
};

export const canApplyRunCompletion = (
  state: RunLifecycleState,
  revision: number
): boolean => (
  !state.completionSuppressed &&
  state.revision === revision
);
