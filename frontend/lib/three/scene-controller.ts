import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { RenderIr } from "../render-ir/types";
import { buildWorldScene, resolveEntityObject, type BuiltWorldScene } from "./build-scene";
import { disposeObjectTree } from "./dispose";

type SelectionListener = (entityId: string | null) => void;

export class SceneController {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(38, 1, 0.01, 10_000);
  private readonly controls: OrbitControls;
  private readonly built: BuiltWorldScene;
  private readonly raycaster = new THREE.Raycaster();
  private readonly pointer = new THREE.Vector2();
  private readonly resizeObserver: ResizeObserver;
  private readonly onSelection: SelectionListener;
  private readonly onContextFailure: (() => void) | undefined;
  private selectionHelper: THREE.Box3Helper | null = null;
  private pointerDown: readonly [number, number] | null = null;
  private currentView: "isometric" | "top" = "isometric";
  private disposed = false;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly renderIr: RenderIr,
    onSelection: SelectionListener,
    onContextFailure?: () => void,
  ) {
    this.onSelection = onSelection;
    this.onContextFailure = onContextFailure;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x131718, 1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.camera.up.set(0, 0, 1);
    this.built = buildWorldScene(renderIr);
    this.scene.add(this.built.root);
    this.scene.add(new THREE.HemisphereLight(0xf8f2e7, 0x273032, 2.4));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.8);
    keyLight.position.set(-8, -10, 14);
    keyLight.castShadow = true;
    this.scene.add(keyLight);

    const gridSize = Math.max(
      renderIr.bounds.max[0] - renderIr.bounds.min[0],
      renderIr.bounds.max[1] - renderIr.bounds.min[1],
      10,
    );
    const grid = new THREE.GridHelper(gridSize * 1.6, 20, 0x526063, 0x2c3537);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = renderIr.bounds.min[2] - 0.01;
    grid.userData.selectable = false;
    this.scene.add(grid);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    this.controls.minDistance = 0.2;
    this.controls.maxDistance = Math.max(gridSize * 8, 40);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas);
    canvas.addEventListener("pointerdown", this.handlePointerDown);
    canvas.addEventListener("pointerup", this.handlePointer);
    canvas.addEventListener("keydown", this.handleKeyDown);
    canvas.addEventListener("webglcontextlost", this.handleContextLost);
    this.resize();
    this.fit("isometric");
    this.renderer.setAnimationLoop(this.render);
  }

  setFloor(floorId: string | null): void {
    for (const [id, group] of this.built.floorGroups) group.visible = floorId === null || id === floorId;
    this.clearSelection();
    this.fit(this.currentView, true);
  }

  selectEntity(entityId: string | null): void {
    this.removeSelectionHelper();
    if (entityId === null) {
      this.onSelection(null);
      return;
    }
    const object = this.built.entityObjects.get(entityId);
    if (!object || !object.visible || !this.isEffectivelyVisible(object)) {
      this.onSelection(null);
      return;
    }
    const box = new THREE.Box3().setFromObject(object);
    if (!box.isEmpty()) {
      this.selectionHelper = new THREE.Box3Helper(box, 0xf0b45c);
      this.selectionHelper.userData.selectable = false;
      this.scene.add(this.selectionHelper);
    }
    this.onSelection(entityId);
  }

  viewIsometric(): void {
    this.currentView = "isometric";
    this.fit("isometric", true);
  }

  viewTop(): void {
    this.currentView = "top";
    this.fit("top", true);
  }

  fitVisible(): void {
    this.fit(this.currentView, true);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.renderer.setAnimationLoop(null);
    this.resizeObserver.disconnect();
    this.canvas.removeEventListener("pointerdown", this.handlePointerDown);
    this.canvas.removeEventListener("pointerup", this.handlePointer);
    this.canvas.removeEventListener("keydown", this.handleKeyDown);
    this.canvas.removeEventListener("webglcontextlost", this.handleContextLost);
    this.removeSelectionHelper();
    this.controls.dispose();
    disposeObjectTree(this.scene);
    this.renderer.renderLists.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }

  private readonly render = (): void => {
    if (this.disposed) return;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };

  private readonly handlePointer = (event: PointerEvent): void => {
    const start = this.pointerDown;
    this.pointerDown = null;
    if (start && Math.hypot(event.clientX - start[0], event.clientY - start[1]) > 5) return;
    const rectangle = this.canvas.getBoundingClientRect();
    if (rectangle.width <= 0 || rectangle.height <= 0) return;
    this.pointer.set(
      ((event.clientX - rectangle.left) / rectangle.width) * 2 - 1,
      -((event.clientY - rectangle.top) / rectangle.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObject(this.built.root, true).find((candidate) => {
      const entity = resolveEntityObject(candidate.object);
      return entity !== null && this.isEffectivelyVisible(entity);
    });
    const entity = resolveEntityObject(hit?.object ?? null);
    this.selectEntity(typeof entity?.userData.entityId === "string" ? entity.userData.entityId : null);
  };

  private readonly handlePointerDown = (event: PointerEvent): void => {
    this.pointerDown = [event.clientX, event.clientY];
  };

  private readonly handleKeyDown = (event: KeyboardEvent): void => {
    if (event.key === "Escape") this.clearSelection();
  };

  private readonly handleContextLost = (event: Event): void => {
    event.preventDefault();
    this.clearSelection();
    this.onContextFailure?.();
  };

  private resize(): void {
    const width = Math.max(this.canvas.clientWidth, 1);
    const height = Math.max(this.canvas.clientHeight, 1);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  private fit(view: "isometric" | "top", visibleOnly = false): void {
    const box = visibleOnly ? this.visibleBounds() : new THREE.Box3(
      new THREE.Vector3(...this.renderIr.bounds.min),
      new THREE.Vector3(...this.renderIr.bounds.max),
    );
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const span = Math.max(size.x, size.y, size.z, 1);
    const distance = span * 1.65;
    this.controls.target.copy(center);
    if (view === "top") {
      this.camera.position.set(center.x, center.y, center.z + distance * 1.3);
    } else {
      this.camera.position.set(
        center.x + distance,
        center.y - distance,
        center.z + distance * 0.82,
      );
    }
    this.camera.near = Math.max(distance / 1000, 0.01);
    this.camera.far = distance * 20;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  private visibleBounds(): THREE.Box3 {
    const box = new THREE.Box3();
    for (const group of this.built.floorGroups.values()) {
      if (group.visible) box.expandByObject(group);
    }
    return box;
  }

  private isEffectivelyVisible(object: THREE.Object3D): boolean {
    let current: THREE.Object3D | null = object;
    while (current) {
      if (!current.visible) return false;
      current = current.parent;
    }
    return true;
  }

  private clearSelection(): void {
    this.removeSelectionHelper();
    this.onSelection(null);
  }

  private removeSelectionHelper(): void {
    if (!this.selectionHelper) return;
    this.scene.remove(this.selectionHelper);
    this.selectionHelper.geometry.dispose();
    const materials = Array.isArray(this.selectionHelper.material)
      ? this.selectionHelper.material
      : [this.selectionHelper.material];
    for (const material of materials) material.dispose();
    this.selectionHelper = null;
  }
}
