import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { disposeObjectTree } from "../lib/three/dispose";

describe("disposeObjectTree", () => {
  it("disposes shared textures, materials, and geometries exactly once and clears the tree", () => {
    const root = new THREE.Group();
    const nested = new THREE.Group();
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const texture = new THREE.Texture();
    const material = new THREE.MeshBasicMaterial({ map: texture });
    const geometryDispose = vi.spyOn(geometry, "dispose");
    const textureDispose = vi.spyOn(texture, "dispose");
    const materialDispose = vi.spyOn(material, "dispose");

    root.add(new THREE.Mesh(geometry, [material, material]));
    nested.add(new THREE.Mesh(geometry, material));
    root.add(nested);

    disposeObjectTree(root);

    expect(textureDispose).toHaveBeenCalledOnce();
    expect(materialDispose).toHaveBeenCalledOnce();
    expect(geometryDispose).toHaveBeenCalledOnce();
    expect(root.children).toHaveLength(0);

    disposeObjectTree(root);
    expect(textureDispose).toHaveBeenCalledOnce();
    expect(materialDispose).toHaveBeenCalledOnce();
    expect(geometryDispose).toHaveBeenCalledOnce();
  });
});
