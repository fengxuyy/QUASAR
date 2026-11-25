
import React, { useRef, useEffect, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Maximize2, Minimize2, Settings, RotateCcw, Camera } from 'lucide-react';
import { generateSceneFromProcessed } from '../../utils/sceneGenerator';
import type { SceneData, ProcessedStructure } from '../../utils/sceneGenerator';
import { GlassDropdown } from '../UI/GlassDropdown';
import { ToggleSwitch } from '../UI/ToggleSwitch';

// Helper to determine if a color is light (for text contrast)
function isLightColor(hexColor: string): boolean {
  const hex = hexColor.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  // Using relative luminance formula
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.5;
}

function disposeObject3D(object: THREE.Object3D) {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    mesh.geometry?.dispose?.();
    const material = mesh.material;
    if (Array.isArray(material)) {
      material.forEach(item => item.dispose?.());
    } else {
      material?.dispose?.();
    }
  });
}

interface CrystalStructureViewerProps {
  cifContent: string;
  fileName?: string;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

type UnitCellType = 'input' | 'primitive' | 'conventional' | 'reduced_niggli' | 'reduced_lll';
type BondingStrategy = 'jmol' | 'crystalnn';
type UnitCellRepeats = [number, number, number];

const MAX_UNIT_CELL_REPEAT = 4;

function clampUnitCellRepeat(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.max(1, Math.min(MAX_UNIT_CELL_REPEAT, Math.round(value)));
}

export const CrystalStructureViewer: React.FC<CrystalStructureViewerProps> = ({
  cifContent: initialCifContent,
  fileName,
  isExpanded = false,
  onToggleExpand
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);

  const [showSettings, setShowSettings] = useState(false);
  const [unitCellType, setUnitCellType] = useState<UnitCellType>('primitive');
  const [bondingStrategy, setBondingStrategy] = useState<BondingStrategy>('jmol');
  const [unitCellRepeats, setUnitCellRepeats] = useState<UnitCellRepeats>([1, 1, 1]);
  const [drawImageAtoms, setDrawImageAtoms] = useState(true);
  const [bondedSitesOutside, setBondedSitesOutside] = useState(true);
  const [showUnitCellBoundary, setShowUnitCellBoundary] = useState(true);
  const [showPolyhedra, setShowPolyhedra] = useState(true);

  const [processedStructure, setProcessedStructure] = useState<ProcessedStructure | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elementColors, setElementColors] = useState<{ [symbol: string]: string }>({});

  // Initialize Three.js
  useEffect(() => {
    if (!mountRef.current) return;

    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xffffff);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(10, 10, 10);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    mountRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controlsRef.current = controls;

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10, 10, 10);
    scene.add(dirLight);

    const renderScene = () => {
      renderer.render(scene, camera);
    };
    controls.addEventListener('change', renderScene);
    renderScene();

    const resizeObserver = new ResizeObserver(() => {
        if (!mountRef.current || !cameraRef.current || !rendererRef.current) return;
        const w = mountRef.current.clientWidth;
        const h = mountRef.current.clientHeight;
        if (w === 0 || h === 0) return;

	        cameraRef.current.aspect = w / h;
	        cameraRef.current.updateProjectionMatrix();
	        rendererRef.current.setSize(w, h);
          rendererRef.current.render(scene, camera);
	    });

    const mountElement = mountRef.current;
    resizeObserver.observe(mountElement);

    return () => {
      resizeObserver.disconnect();
      controls.removeEventListener('change', renderScene);
      if (mountElement && rendererRef.current) {
        mountElement.removeChild(rendererRef.current.domElement);
      }
      rendererRef.current?.dispose();
    };
  }, []);

  // Reset settings when CIF changes
  useEffect(() => {
      setUnitCellType('primitive');
      setBondingStrategy('jmol');
      setUnitCellRepeats([1, 1, 1]);
      setDrawImageAtoms(true);
      setBondedSitesOutside(true);
      setShowUnitCellBoundary(true);
      setShowPolyhedra(true);
  }, [initialCifContent]);

  // Effect to process structure via API
  useEffect(() => {
      let cancelled = false;
      const controller = new AbortController();
      const processStructure = async () => {
          setIsLoading(true);
          setError(null);
          try {
              const response = await fetch('/api/structure/process', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  signal: controller.signal,
                  body: JSON.stringify({
                      cifContent: initialCifContent,
                      cellType: unitCellType,
                      bonding: bondingStrategy,
                      unit_cell_repeats: unitCellRepeats,
                      draw_image_atoms: drawImageAtoms,
                      bonded_sites_outside_unit_cell: bondedSitesOutside
                  })
              });

              if (!response.ok) {
                  throw new Error(`Processing failed: ${response.statusText}`);
              }

              const result = await response.json();
              if (result.error) {
                  throw new Error(result.error);
              }

              if (!cancelled) {
                  setProcessedStructure(result as ProcessedStructure);
              }

          } catch (e) {
              if (controller.signal.aborted) return;
              console.error("Structure processing error:", e);
              if (!cancelled) {
                  setError((e as Error).message);
              }
          } finally {
              if (!cancelled) {
                  setIsLoading(false);
              }
          }
      };

      if (initialCifContent) {
          processStructure();
      }
      return () => {
          cancelled = true;
          controller.abort();
      };
  }, [unitCellType, bondingStrategy, unitCellRepeats, drawImageAtoms, bondedSitesOutside, initialCifContent]);


  // Update Scene when processedStructure changes
  const lastStructureRef = useRef<string>('');

  useEffect(() => {
    if (!sceneRef.current || !processedStructure) return;

    const scene = sceneRef.current;

    // Check if truly new structure (more sites, different bonds, etc.)
    const structureKey = JSON.stringify({
        siteCount: processedStructure.sites.length,
        bondCount: processedStructure.bonds.length,
        unitCell: processedStructure.unit_cell
    });
    const isNewStructure = lastStructureRef.current !== structureKey;
    lastStructureRef.current = structureKey;

    // Clear existing structure parts
    const childrenToRemove: THREE.Object3D[] = [];
    scene.traverse((child) => {
      if (child.name === 'structure_part') {
        childrenToRemove.push(child);
      }
    });
    childrenToRemove.forEach(child => {
      scene.remove(child);
      disposeObject3D(child);
    });

    try {
      const data: SceneData = generateSceneFromProcessed(processedStructure, showPolyhedra);

      // Update element colors for legend
      setElementColors(data.colorScheme || {});

      const structureGroup = new THREE.Group();
      structureGroup.name = 'structure_part';

      // Spheres
      data.spheres.forEach(s => {
        const geometry = new THREE.SphereGeometry(s.radius, 32, 32);
        const material = new THREE.MeshPhysicalMaterial({
          color: s.color,
          roughness: 0.2,
          metalness: 0.1
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(...s.position);
        structureGroup.add(mesh);
      });

      // Bonds (Cylinders)
      data.cylinders.forEach(c => {
        const start = new THREE.Vector3(...c.start);
        const end = new THREE.Vector3(...c.end);
        const direction = new THREE.Vector3().subVectors(end, start);
        const length = direction.length();

        if (length < 0.01) return; // Skip zero-length bonds

        const geometry = new THREE.CylinderGeometry(c.radius, c.radius, length, 16);
        const material = new THREE.MeshStandardMaterial({ color: c.color });
        const mesh = new THREE.Mesh(geometry, material);

        const center = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
        mesh.position.copy(center);
        mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());

        structureGroup.add(mesh);
      });

      // Unit Cell (Lines)
      if (showUnitCellBoundary && data.lines.length > 0) {
          const points: THREE.Vector3[] = [];
          data.lines.forEach(l => {
              points.push(new THREE.Vector3(...l.start));
              points.push(new THREE.Vector3(...l.end));
          });
          const geometry = new THREE.BufferGeometry().setFromPoints(points);
          const material = new THREE.LineBasicMaterial({ color: 0x000000 });
          const lineSegments = new THREE.LineSegments(geometry, material);
          structureGroup.add(lineSegments);
      }

      // Polyhedra (transparent meshes)
      data.polyhedra.forEach(poly => {
        const geometry = new THREE.BufferGeometry();

        // Flatten vertices
        const positions: number[] = [];
        poly.faces.forEach(face => {
          // Each face is a triangle (3 vertex indices)
          for (let i = 0; i < 3; i++) {
            const vertIdx = face[i];
            if (vertIdx >= 0 && vertIdx < poly.vertices.length) {
              const v = poly.vertices[vertIdx];
              positions.push(v[0], v[1], v[2]);
            }
          }
        });

        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geometry.computeVertexNormals();

        const material = new THREE.MeshPhysicalMaterial({
          color: poly.color,
          transparent: true,
          opacity: poly.opacity,
          side: THREE.DoubleSide,
          roughness: 0.5,
          metalness: 0.0
        });

        const mesh = new THREE.Mesh(geometry, material);
        structureGroup.add(mesh);
      });

      scene.add(structureGroup);

      // Center camera on new structure
      if (isNewStructure) {
        const box = new THREE.Box3().setFromObject(structureGroup);
        if (!box.isEmpty()) {
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);

            if (controlsRef.current && cameraRef.current) {
                controlsRef.current.target.copy(center);

                const fov = cameraRef.current.fov * (Math.PI / 180);
                let cameraZ = Math.abs(maxDim / (2 * Math.tan(fov / 2)));
                cameraZ *= 2.0;

                const offset = new THREE.Vector3(1, 1, 1).normalize().multiplyScalar(cameraZ);
                cameraRef.current.position.copy(center).add(offset);
                cameraRef.current.lookAt(center);

	                controlsRef.current.update();
	                controlsRef.current.saveState();
	            }
	        }
	      }

      if (rendererRef.current && cameraRef.current) {
        rendererRef.current.render(scene, cameraRef.current);
      }

    } catch (e) {
      console.error("Error generating scene:", e);
    }
  }, [processedStructure, showPolyhedra, showUnitCellBoundary]);

  const handleResetView = () => {
     if (controlsRef.current) {
         controlsRef.current.reset();
     }
  };

  const handleSnapshot = () => {
      if (rendererRef.current && sceneRef.current && cameraRef.current) {
          rendererRef.current.render(sceneRef.current, cameraRef.current);
          const dataUrl = rendererRef.current.domElement.toDataURL('image/png');
          const link = document.createElement('a');
          link.download = `${fileName?.replace('.cif', '') || 'structure'}_snapshot.png`;
          link.href = dataUrl;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
      }
  };

  const handleUnitCellRepeatChange = (axisIndex: number, value: number) => {
      setUnitCellRepeats((current) => {
          const next = [...current] as UnitCellRepeats;
          next[axisIndex] = clampUnitCellRepeat(value);
          return next;
      });
  };

  const toolbarButtonClass = `
    p-2 rounded-lg transition-all duration-200
    bg-white/80 hover:bg-white text-slate-600 hover:text-blue-600
    shadow-sm hover:shadow-md backdrop-blur-sm
    border border-white/50
  `;

  return (
    <div
      className="relative w-full h-full rounded-xl overflow-hidden bg-white"
      style={{ minHeight: '400px' }}
    >
      {isLoading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/60 backdrop-blur-sm">
          <div className="relative w-16 h-16">
            {/* Central atom */}
            <div className="absolute top-1/2 left-1/2 w-4 h-4 -mt-2 -ml-2 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 shadow-lg" />

            {/* Orbiting electrons */}
            <div className="absolute inset-0 animate-spin" style={{ animationDuration: '2s' }}>
              <div className="absolute top-0 left-1/2 w-2.5 h-2.5 -ml-1.25 rounded-full bg-gradient-to-br from-rose-300 to-rose-400 shadow-md" />
            </div>
            <div className="absolute inset-0 animate-spin" style={{ animationDuration: '2.5s', animationDirection: 'reverse' }}>
              <div className="absolute bottom-0 left-1/2 w-2.5 h-2.5 -ml-1.25 rounded-full bg-gradient-to-br from-amber-300 to-amber-400 shadow-md" />
            </div>
            <div className="absolute inset-0 animate-spin" style={{ animationDuration: '3s' }}>
              <div className="absolute top-1/2 left-0 w-2.5 h-2.5 -mt-1.25 rounded-full bg-gradient-to-br from-emerald-300 to-emerald-400 shadow-md" />
            </div>

            {/* Orbital rings */}
            <div className="absolute inset-0 border-2 border-slate-200/50 rounded-full" />
            <div className="absolute inset-2 border border-slate-200/30 rounded-full" />
          </div>
        </div>
      )}

      {error && (
        <div className="absolute bottom-4 left-4 right-4 z-20 bg-red-50 px-4 py-2 rounded-lg shadow-lg border border-red-200 flex items-center justify-between">
           <span className="text-xs text-red-600">{error}</span>
           <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 ml-2">×</button>
        </div>
      )}

      {/* Toolbar */}
      <div className="absolute top-3 right-3 z-10 flex items-center gap-2">
        <button onClick={handleResetView} className={toolbarButtonClass} title="Reset View">
          <RotateCcw size={18} />
        </button>
        <button onClick={handleSnapshot} className={toolbarButtonClass} title="Take Snapshot">
          <Camera size={18} />
        </button>
        <button
          onClick={() => setShowSettings(!showSettings)}
          className={`${toolbarButtonClass} ${showSettings ? 'bg-blue-100 text-blue-600' : ''}`}
          title="Settings"
        >
          <Settings size={18} />
        </button>
        {onToggleExpand && (
          <button onClick={onToggleExpand} className={toolbarButtonClass} title={isExpanded ? "Collapse" : "Expand"}>
            {isExpanded ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </button>
        )}
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="absolute top-14 right-3 z-10 bg-white/90 backdrop-blur-md rounded-xl shadow-lg border border-white/40 p-4 min-w-[280px] animate-dropdown-in">
           <h4 className="text-sm font-semibold text-slate-700 mb-4">Visualization Settings</h4>

           <div className="space-y-4">
               <GlassDropdown
                   label="Unit Cell"
                   value={unitCellType}
                   onChange={(v) => setUnitCellType(v as UnitCellType)}
                   disabled={isLoading}
                   options={[
                       { value: 'input', label: 'Input Cell' },
                       { value: 'primitive', label: 'Primitive Cell' },
                       { value: 'conventional', label: 'Conventional Cell' },
                       { value: 'reduced_niggli', label: 'Niggli Reduced' },
                       { value: 'reduced_lll', label: 'LLL Reduced' }
                   ]}
               />

               <div>
                   <label className="block text-xs font-medium text-slate-500 mb-1">
                       Unit Cell Duplicates
                   </label>
                   <div className="grid grid-cols-3 gap-2">
                       {(['a', 'b', 'c'] as const).map((axis, axisIndex) => (
                           <label key={axis} className="block">
                               <span className="block text-[11px] font-semibold uppercase text-slate-500 mb-1">
                                   {axis}
                               </span>
                               <input
                                   type="number"
                                   min={1}
                                   max={MAX_UNIT_CELL_REPEAT}
                                   step={1}
                                   value={unitCellRepeats[axisIndex]}
                                   onChange={(event) => handleUnitCellRepeatChange(axisIndex, Number(event.target.value))}
                                   disabled={isLoading}
                                   className="h-9 w-full rounded-lg border border-white/30 bg-white/20 px-2 text-sm font-medium text-slate-700 shadow-sm outline-none transition focus:border-blue-300/60 focus:ring-2 focus:ring-blue-400/50 disabled:cursor-not-allowed disabled:opacity-50"
                               />
                           </label>
                       ))}
                   </div>
               </div>

               <GlassDropdown
                   label="Bonding Algorithm"
                   value={bondingStrategy}
                   onChange={(v) => setBondingStrategy(v as BondingStrategy)}
                   disabled={isLoading}
                   options={[
                       { value: 'jmol', label: 'Jmol' },
                       { value: 'crystalnn', label: 'CrystalNN' }
                   ]}
               />

               <div className="border-t border-slate-200/50 pt-4 space-y-3">
                   <div className="flex items-center justify-between">
                       <span className="text-xs font-medium text-slate-600">Draw Image Atoms</span>
                       <ToggleSwitch
                           enabled={drawImageAtoms}
                           onChange={setDrawImageAtoms}
                           label="Draw Image Atoms"
                       />
                   </div>

                   <div className="flex items-center justify-between">
                       <span className="text-xs font-medium text-slate-600">Bonded Sites Outside Cell</span>
                       <ToggleSwitch
                           enabled={bondedSitesOutside}
                           onChange={setBondedSitesOutside}
                           label="Bonded Sites Outside Cell"
                       />
                   </div>

                   <div className="flex items-center justify-between">
                       <span className="text-xs font-medium text-slate-600">Show Unit Cell Boundary</span>
                       <ToggleSwitch
                           enabled={showUnitCellBoundary}
                           onChange={setShowUnitCellBoundary}
                           label="Show Unit Cell Boundary"
                       />
                   </div>

                   <div className="flex items-center justify-between">
                       <span className="text-xs font-medium text-slate-600">Show Polyhedra</span>
                       <ToggleSwitch
                           enabled={showPolyhedra}
                           onChange={setShowPolyhedra}
                           label="Show Polyhedra"
                       />
                   </div>
               </div>
           </div>
        </div>
      )}

      {isExpanded && (
        <div className="absolute top-3 left-4 z-10">
          <h3 className="font-medium text-slate-700 bg-white/80 backdrop-blur-sm px-3 py-1.5 rounded-lg shadow-sm border border-white/50">
            {fileName || 'Crystal Structure'}
          </h3>
        </div>
      )}

      {/* Element Legend */}
      {Object.keys(elementColors).length > 0 && (
        <div className="absolute bottom-3 left-3 z-10 bg-white/80 backdrop-blur-md rounded-xl shadow-lg border border-white/40 p-2">
          <div className="flex flex-wrap gap-1.5 max-w-[180px]">
            {Object.entries(elementColors).map(([symbol, color]) => (
              <div
                key={symbol}
                className="flex items-center justify-center rounded-lg px-2.5 py-1 text-xs font-semibold shadow-md transition-transform hover:scale-105"
                style={{
                  backgroundColor: color,
                  color: isLightColor(color) ? '#1f2937' : '#ffffff',
                  minWidth: '36px',
                  textShadow: isLightColor(color) ? 'none' : '0 1px 2px rgba(0,0,0,0.3)'
                }}
              >
                {symbol}
              </div>
            ))}
          </div>
        </div>
      )}

      <div ref={mountRef} className="w-full h-full" />
    </div>
  );
};
