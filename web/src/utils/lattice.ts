
export class Lattice {
  a: number;
  b: number;
  c: number;
  alpha: number;
  beta: number;
  gamma: number;
  
  matrix: number[][];

  constructor(a: number, b: number, c: number, alpha: number, beta: number, gamma: number) {
    this.a = a;
    this.b = b;
    this.c = c;
    this.alpha = alpha;
    this.beta = beta;
    this.gamma = gamma; 
    this.matrix = this.calculateMatrix();
  }

  private calculateMatrix(): number[][] {
    const a = this.a;
    const b = this.b;
    const c = this.c;
    const alphaRad = (this.alpha * Math.PI) / 180;
    const betaRad = (this.beta * Math.PI) / 180;
    const gammaRad = (this.gamma * Math.PI) / 180;

    const v =
      Math.sqrt(
        1 -
          Math.cos(alphaRad) ** 2 -
          Math.cos(betaRad) ** 2 -
          Math.cos(gammaRad) ** 2 +
          2 * Math.cos(alphaRad) * Math.cos(betaRad) * Math.cos(gammaRad)
      );

    const m11 = a;
    const m12 = b * Math.cos(gammaRad);
    const m13 = c * Math.cos(betaRad);
    
    const m21 = 0;
    const m22 = b * Math.sin(gammaRad);
    const m23 = c * (Math.cos(alphaRad) - Math.cos(betaRad) * Math.cos(gammaRad)) / Math.sin(gammaRad);
    
    const m31 = 0;
    const m32 = 0;
    const m33 = (c * v) / Math.sin(gammaRad);

    return [
      [m11, m12, m13],
      [m21, m22, m23],
      [m31, m32, m33]
    ];
  }

  getCartesianCoordinates(fract: [number, number, number]): [number, number, number] {
    const [u, v, w] = fract;
    const m = this.matrix;
    
    const x = m[0][0] * u + m[0][1] * v + m[0][2] * w;
    const y = m[1][0] * u + m[1][1] * v + m[1][2] * w;
    const z = m[2][0] * u + m[2][1] * v + m[2][2] * w;
    
    return [x, y, z];
  }
}
