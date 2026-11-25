
// Modern, web-friendly color palette for crystal structure elements
// Lighter, pastel colors for a softer, more modern aesthetic

// Base palette - lighter, pastel colors
const ELEMENT_COLORS: { [symbol: string]: string } = {
    // Common elements with distinctive lighter colors
    "H": "#F8FAFC",      // Very light gray (hydrogen)
    "C": "#78909C",      // Blue-gray (carbon)
    "N": "#64B5F6",      // Light blue (nitrogen)
    "O": "#EF9A9A",      // Light red/coral (oxygen)
    "F": "#81C784",      // Light green (fluorine)
    "Cl": "#A5D6A7",     // Soft green (chlorine)
    "Br": "#CE93D8",     // Light purple (bromine)
    "I": "#B39DDB",      // Soft violet (iodine)
    "S": "#FFF176",      // Light yellow (sulfur)
    "P": "#FFCC80",      // Light orange (phosphorus)
    
    // Common metals - lighter shades
    "Fe": "#FFAB91",     // Soft coral (iron)
    "Cu": "#FFAB91",     // Soft coral/copper
    "Zn": "#B0BEC5",     // Light gray (zinc)
    "Ca": "#80DEEA",     // Light cyan (calcium)
    "Mg": "#80CBC4",     // Light teal (magnesium)
    "Na": "#B39DDB",     // Soft violet (sodium)
    "K": "#D1C4E9",      // Lavender (potassium)
    "Al": "#CFD8DC",     // Very light gray (aluminum)
    "Si": "#9FA8DA",     // Light indigo (silicon)
    "Ti": "#B0BEC5",     // Light slate (titanium)
    
    // Transition metals - lighter
    "Mn": "#B39DDB",     // Light violet (manganese)
    "Co": "#90CAF9",     // Light blue (cobalt)
    "Ni": "#A5D6A7",     // Soft green (nickel)
    "Mo": "#80DEEA",     // Light cyan (molybdenum)
    "W": "#90A4AE",      // Light slate (tungsten)
    "Cr": "#80CBC4",     // Light teal (chromium)
    "V": "#BCAAA4",      // Light brown (vanadium)
    
    // Rare earths / other - lighter
    "La": "#FFE082",     // Light amber
    "Ce": "#FFF59D",     // Pale yellow
    "Pb": "#90A4AE",     // Light gray (lead)
    "Sn": "#CFD8DC",     // Very light gray (tin)
    "Bi": "#F48FB1",     // Light pink (bismuth)
    "Au": "#FFE082",     // Soft gold
    "Ag": "#E0E0E0",     // Light silver
    "Pt": "#EEEEEE",     // Platinum (light gray)
    "Pd": "#CFD8DC",     // Light gray (palladium)
    
    // Actinides - lighter
    "U": "#80CBC4",      // Light teal (uranium)
    "Th": "#80DEEA",     // Light cyan (thorium)
    
    // Lanthanides - lighter
    "Nd": "#F48FB1",     // Light pink (neodymium)
    "Eu": "#F8BBD9",     // Soft pink (europium)
    "Gd": "#F8BBD9",     // Light pink (gadolinium)
    "Yb": "#E1BEE7",     // Pale purple (ytterbium)
    
    // Alkali - lighter
    "Li": "#E1BEE7",     // Pale purple (lithium)
    "Rb": "#EDE7F6",     // Very light purple (rubidium)
    "Cs": "#F3E5F5",     // Lavender mist (cesium)
    
    // Alkaline earth - lighter
    "Be": "#C8E6C9",     // Pale green (beryllium)
    "Sr": "#B2DFDB",     // Light teal (strontium)
    "Ba": "#A7FFEB",     // Mint (barium)
};

// Fallback palette for elements not in the map - lighter pastel colors
const FALLBACK_PALETTE = [
    "#90CAF9",  // Light blue
    "#A5D6A7",  // Light green
    "#FFE082",  // Light amber
    "#EF9A9A",  // Light red
    "#CE93D8",  // Light purple
    "#80DEEA",  // Light cyan
    "#F48FB1",  // Light pink
    "#FFCC80",  // Light orange
    "#9FA8DA",  // Light indigo
    "#80CBC4",  // Light teal
    "#DCE775",  // Light lime
    "#E1BEE7",  // Pale purple
];

// Extract base element symbol (strip oxidation state like Mo5+ -> Mo)
function getBaseElement(symbol: string): string {
    return symbol.replace(/[0-9+-]+$/, '');
}

export function generateAccessibleColors(elements: string[]): { [symbol: string]: string } {
    const colorScheme: { [symbol: string]: string } = {};
    const usedColors = new Set<string>();
    let fallbackIndex = 0;

    elements.forEach(el => {
        const baseEl = getBaseElement(el);
        
        // Check if we have a predefined color for this element
        if (ELEMENT_COLORS[baseEl]) {
            colorScheme[el] = ELEMENT_COLORS[baseEl];
            usedColors.add(ELEMENT_COLORS[baseEl]);
        } else {
            // Use fallback palette
            const color = FALLBACK_PALETTE[fallbackIndex % FALLBACK_PALETTE.length];
            colorScheme[el] = color;
            usedColors.add(color);
            fallbackIndex++;
        }
    });

    return colorScheme;
}

// Export for use in legend
export function getElementColors(): { [symbol: string]: string } {
    return ELEMENT_COLORS;
}
