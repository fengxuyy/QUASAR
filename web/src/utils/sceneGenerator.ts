
import { getElementRadius } from './elementData';
import { generateAccessibleColors } from './accessibleColors';

export interface SiteData {
  symbol: string;
  position: [number, number, number];
  index: number;
  jimage: [number, number, number];
  label?: string;
}

export interface UnitCellData {
  a: [number, number, number];
  b: [number, number, number];
  c: [number, number, number];
}

export interface PolyhedronData {
  center_idx: number;
  vertices: [number, number, number][];
  faces: number[][];  // Each face is a list of vertex indices
  symbol: string;
}

export interface ProcessedStructure {
  sites: SiteData[];
  bonds: [number, number][];
  unit_cell: UnitCellData;
  polyhedra?: PolyhedronData[];
  error?: string;
}

export interface SceneData {
  spheres: { position: [number, number, number], color: string, radius: number, label: string }[];
  cylinders: { start: [number, number, number], end: [number, number, number], color: string, radius: number }[];
  lines: { start: [number, number, number], end: [number, number, number], color: string }[];
  polyhedra: { vertices: [number, number, number][], faces: number[][], color: string, opacity: number }[];
  colorScheme: { [symbol: string]: string };
}

/**
 * Generate scene data from processed structure (new API format)
 */
export function generateSceneFromProcessed(processed: ProcessedStructure, showPolyhedra: boolean = false): SceneData {
  const spheres: SceneData['spheres'] = [];
  const lines: SceneData['lines'] = [];
  const cylinders: SceneData['cylinders'] = [];
  const polyhedra: SceneData['polyhedra'] = [];

  // Helper to extract base element (strip oxidation state like K+ -> K, O2- -> O)
  const getBaseElement = (symbol: string): string => symbol.replace(/[0-9+-]+$/, '');

  // Determine colors using accessible scheme
  const uniqueElements = Array.from(new Set(processed.sites.map(s => s.symbol)));
  const accessibleColorMap = generateAccessibleColors(uniqueElements);

  // Create normalized color scheme for legend (base element -> color)
  const normalizedColorScheme: { [symbol: string]: string } = {};
  uniqueElements.forEach(el => {
    const baseEl = getBaseElement(el);
    if (!normalizedColorScheme[baseEl]) {
      normalizedColorScheme[baseEl] = accessibleColorMap[el];
    }
  });

  // 1. Generate Atoms (Spheres)
  processed.sites.forEach((site) => {
    const color = accessibleColorMap[site.symbol] || '#808080';
    spheres.push({
      position: site.position,
      color: color,
      radius: getElementRadius(site.symbol) * 0.4,
      label: `${site.symbol}${site.index}`
    });
  });

  // 2. Generate Unit Cell Box (Lines)
  const { a, b, c } = processed.unit_cell;
  
  // Helper to add vectors
  const add = (v1: number[], v2: number[]): [number, number, number] => 
    [v1[0] + v2[0], v1[1] + v2[1], v1[2] + v2[2]];
  
  const origin: [number, number, number] = [0, 0, 0];
  const corners = [
    origin,                    // 0: origin
    a,                         // 1: a
    b,                         // 2: b
    c,                         // 3: c
    add(a, b),                 // 4: a+b
    add(a, c),                 // 5: a+c
    add(b, c),                 // 6: b+c
    add(add(a, b), c)          // 7: a+b+c
  ] as [number, number, number][];

  const segments = [
    [0, 1], [0, 2], [0, 3], // from origin
    [1, 4], [1, 5],         // from a
    [2, 4], [2, 6],         // from b
    [3, 5], [3, 6],         // from c
    [4, 7], [5, 7], [6, 7]  // to corner
  ];

  segments.forEach(([i, j]) => {
    lines.push({
      start: corners[i],
      end: corners[j],
      color: '#000000'
    });
  });

  // 3. Generate Bonds (Cylinders)
  processed.bonds.forEach(([i, j]) => {
    if (i >= 0 && i < processed.sites.length && j >= 0 && j < processed.sites.length) {
      const site1 = processed.sites[i];
      const site2 = processed.sites[j];
      cylinders.push({
        start: site1.position,
        end: site2.position,
        color: '#808080',
        radius: 0.1
      });
    }
  });

  // 4. Generate Polyhedra (if enabled)
  if (showPolyhedra && processed.polyhedra) {
    processed.polyhedra.forEach((poly) => {
      const color = accessibleColorMap[poly.symbol] || '#808080';
      polyhedra.push({
        vertices: poly.vertices,
        faces: poly.faces,
        color: color,
        opacity: 0.25
      });
    });
  }

  return { spheres, lines, cylinders, polyhedra, colorScheme: normalizedColorScheme };
}
