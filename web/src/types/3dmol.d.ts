declare module '3dmol' {
  export function createViewer(
    element: HTMLElement,
    config?: {
      backgroundColor?: string;
      antialias?: boolean;
      cartoonQuality?: number;
    }
  ): GLViewer;

  export interface GLViewer {
    addModel(data: string, format: string): GLModel;
    addUnitCell(model?: GLModel, spec?: {
      box?: { color?: string; opacity?: number };
      alabel?: string;
      blabel?: string;
      clabel?: string;
      astyle?: { hidden?: boolean };
      bstyle?: { hidden?: boolean };
      cstyle?: { hidden?: boolean };
    }): void;
    setStyle(sel: object, style: object): void;
    zoomTo(): void;
    render(): void;
    clear(): void;
    resize(): void;
  }

  export interface GLModel {
    setStyle(sel: object, style: object): void;
  }
}
