
interface Atom {
  label: string;
  symbol: string;
  x: number;
  y: number;
  z: number;
}

interface CrystalStructure {
  a: number;
  b: number;
  c: number;
  alpha: number;
  beta: number;
  gamma: number;
  atoms: Atom[];
}

export function parseCIF(cifContent: string): CrystalStructure {
  const lines = cifContent.split('\n');
  let a = 0, b = 0, c = 0;
  let alpha = 90, beta = 90, gamma = 90;
  
  const atoms: Atom[] = [];
  
  let inAtomLoop = false;
  let headers: string[] = [];
  
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i].trim();
    if (!line || line.startsWith('#')) continue;
    
    // Remove comments inline
    if (line.includes('#')) {
      line = line.split('#')[0].trim();
    }

    if (line.startsWith('_cell_length_a')) a = parseFloat(line.split(/\s+/)[1]);
    if (line.startsWith('_cell_length_b')) b = parseFloat(line.split(/\s+/)[1]);
    if (line.startsWith('_cell_length_c')) c = parseFloat(line.split(/\s+/)[1]);
    if (line.startsWith('_cell_angle_alpha')) alpha = parseFloat(line.split(/\s+/)[1]);
    if (line.startsWith('_cell_angle_beta')) beta = parseFloat(line.split(/\s+/)[1]);
    if (line.startsWith('_cell_angle_gamma')) gamma = parseFloat(line.split(/\s+/)[1]);

    if (line.startsWith('loop_')) {
      // Check if this loop is for atoms
      headers = [];
      let nextLineIndex = i + 1;
      while (nextLineIndex < lines.length) {
        const nextLine = lines[nextLineIndex].trim();
        if (nextLine.startsWith('_')) {
          headers.push(nextLine);
          nextLineIndex++;
        } else {
          break;
        }
      }
      
      const atomHeaders = headers.filter(h => h.startsWith('_atom_site_'));
      if (atomHeaders.length > 0) {
        inAtomLoop = true;
        i = nextLineIndex - 1; // Move outer loop
        continue;
      } else {
        inAtomLoop = false;
      }
    }

    if (inAtomLoop) {
       // Check if line looks like data (not starting with underscore or loop_)
       if (line.startsWith('_') || line.startsWith('loop_')) {
         inAtomLoop = false;
         // Re-evaluate this line in next iteration
         i--; 
         continue;
       }
       
       const parts = line.split(/\s+/);
       if (parts.length < headers.length) continue; // Skip incomplete lines
       
       const atom: any = {};
       
       headers.forEach((header, index) => {
         // handle ( value ) uncertainty notation if present, though parseFloat handles it usually stops at (
         // Actually parseFloat("1.23(4)") is 1.23.
         const valWithUncertainty = parts[index];
         // Remove parenthesis for clean parsing if needed, but parseFloat usually works fine for prefix
         const valStr = valWithUncertainty.split('(')[0];
         
         if (header === '_atom_site_label') atom.label = parts[index];
         if (header === '_atom_site_type_symbol') atom.symbol = parts[index];
         if (header === '_atom_site_fract_x') atom.x = parseFloat(valStr);
         if (header === '_atom_site_fract_y') atom.y = parseFloat(valStr);
         if (header === '_atom_site_fract_z') atom.z = parseFloat(valStr);
       });
       
       if (!atom.symbol && atom.label) {
         // Try to extract symbol from label
         atom.symbol = atom.label.replace(/[0-9+-]/g, '');
       }

       if (atom.x !== undefined && atom.y !== undefined && atom.z !== undefined) {
         atoms.push(atom as Atom);
       }
    }
  }

  return { a, b, c, alpha, beta, gamma, atoms };
}
