declare module "ogl/src/index.js" {
  export class Renderer {
    constructor(options?: Record<string, unknown>);
    gl: WebGLRenderingContext & { canvas: HTMLCanvasElement };
    dpr?: number;
    setSize(width: number, height: number): void;
    render(options: { scene: unknown }): void;
    destroy?(): void;
  }

  export class Program {
    constructor(gl: WebGLRenderingContext, options?: Record<string, unknown>);
    remove?(): void;
  }

  export class Triangle {
    constructor(gl: WebGLRenderingContext);
    remove?(): void;
  }

  export class Mesh {
    constructor(gl: WebGLRenderingContext, options?: Record<string, unknown>);
    remove?(): void;
  }
}
