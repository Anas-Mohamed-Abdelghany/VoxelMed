import React, { useRef, useMemo, useEffect, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, GizmoHelper, GizmoViewport } from '@react-three/drei';
import * as THREE from 'three';
import { getVolumeData } from '../api/client';
import useStore from '../store/useStore';

// ---------------------------------------------------------------------------
// GLSL 3.0 Raymarching Shader — Multi-label + Intensity Fallback
// ---------------------------------------------------------------------------
const vertexShader = `
  out vec3 vPosition;
  out vec3 vCameraPosLocal;

  void main() {
    vPosition = position;
    vCameraPosLocal = (inverse(modelMatrix) * vec4(cameraPosition, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const fragmentShader = `
  precision highp float;
  precision highp sampler3D;

  in vec3 vPosition;
  in vec3 vCameraPosLocal;
  out vec4 fragColor;

  uniform sampler3D u_data;
  uniform sampler3D u_mask;
  uniform sampler2D u_lut;
  uniform float u_hasMask;
  uniform float u_density;
  uniform float u_threshold;
  uniform vec3 u_boxSize;

  uniform vec3 u_clipEnabled;
  uniform vec3 u_clipPos;
  uniform vec3 u_clipFlipped;
  uniform float u_boxCrop;

  uniform float u_selectedLabel;
  uniform float u_organOpacity;
  uniform float u_backgroundOpacity;

  vec2 hitBox(vec3 orig, vec3 dir, vec3 bMin, vec3 bMax) {
    vec3 invDir = 1.0 / dir;
    vec3 t0 = (bMin - orig) * invDir;
    vec3 t1 = (bMax - orig) * invDir;
    vec3 tmin = min(t0, t1);
    vec3 tmax = max(t0, t1);
    float tNear = max(max(tmin.x, tmin.y), tmin.z);
    float tFar  = min(min(tmax.x, tmax.y), tmax.z);
    return vec2(tNear, tFar);
  }

  bool isClipped(vec3 uvw) {
    if (u_clipEnabled.x > 0.5) {
      float p = u_clipFlipped.x > 0.5 ? 1.0 - u_clipPos.x : u_clipPos.x;
      if (uvw.x < p) return true;
    }
    if (u_clipEnabled.y > 0.5) {
      float p = u_clipFlipped.y > 0.5 ? 1.0 - u_clipPos.y : u_clipPos.y;
      if (uvw.y < p) return true;
    }
    if (u_clipEnabled.z > 0.5) {
      float p = u_clipFlipped.z > 0.5 ? 1.0 - u_clipPos.z : u_clipPos.z;
      if (uvw.z < p) return true;
    }
    return false;
  }

  vec4 getTissueColor(float val) {
    vec3 col = vec3(0.0);
    float a = 0.0;
    if (val < u_threshold) {
      return vec4(0.0);
    } else if (val < 0.22) {
      col = vec3(0.85, 0.72, 0.45);
      a = (val - u_threshold) * 0.35;
    } else if (val < 0.50) {
      float t = (val - 0.22) / 0.28;
      vec3 roseBrain = vec3(0.92, 0.58, 0.65);
      vec3 burgundy = vec3(0.72, 0.22, 0.22);
      col = mix(roseBrain, burgundy, t * 0.5);
      a = 0.50 + t * 0.35;
    } else if (val < 0.70) {
      col = vec3(0.85, 0.12, 0.16);
      a = 0.75;
    } else {
      float t = (val - 0.70) / 0.30;
      col = mix(vec3(0.95, 0.92, 0.84), vec3(1.0, 0.98, 0.95), t);
      a = 0.92;
    }
    return vec4(col, a);
  }

  vec3 computeNormal(vec3 uvw) {
    vec3 eps = vec3(0.006);
    float gx = texture(u_data, uvw + vec3(eps.x, 0.0, 0.0)).r - texture(u_data, uvw - vec3(eps.x, 0.0, 0.0)).r;
    float gy = texture(u_data, uvw + vec3(0.0, eps.y, 0.0)).r - texture(u_data, uvw - vec3(0.0, eps.y, 0.0)).r;
    float gz = texture(u_data, uvw + vec3(0.0, 0.0, eps.z)).r - texture(u_data, uvw - vec3(0.0, 0.0, eps.z)).r;
    return -normalize(vec3(gx, gy, gz) + 0.0001);
  }

  void main() {
    vec3 bMin = -u_boxSize * 0.5;
    vec3 bMax =  u_boxSize * 0.5;

    vec3 rayDir = normalize(vPosition - vCameraPosLocal);
    vec2 hit = hitBox(vCameraPosLocal, rayDir, bMin, bMax);
    if (hit.x > hit.y || hit.y < 0.0) discard;

    float tStart = max(hit.x, 0.0);
    float tEnd   = hit.y;
    float stepLength = 0.005;
    vec4 accum = vec4(0.0);
    vec3 lightDir = normalize(vec3(0.5, 0.8, 0.6));

    for (float t = tStart; t < tEnd; t += stepLength) {
      if (accum.a >= 0.95) break;

      vec3 localPos = vCameraPosLocal + rayDir * t;
      vec3 uvw = (localPos - bMin) / u_boxSize;

      if (any(lessThan(uvw, vec3(0.0))) || any(greaterThan(uvw, vec3(1.0)))) continue;
      if (isClipped(uvw)) continue;

      float val = texture(u_data, uvw).r;

      // --- Multi-label path ---
      if (u_hasMask > 0.5) {
        float label = texture(u_mask, uvw).r * 255.0;

        if (label > 0.5) {
          vec2 lutUV = vec2((label + 0.5) / 256.0, 0.5);
          vec4 labelColor = texture(u_lut, lutUV);

          // Determine opacity: selected organ uses organOpacity, rest uses backgroundOpacity
          float opacityMult = u_backgroundOpacity;
          if (u_selectedLabel < 0.5) {
            // No organ selected — all organs at full opacity
            opacityMult = 1.0;
          } else if (abs(label - u_selectedLabel) < 0.5) {
            opacityMult = u_organOpacity;
          }

          if (labelColor.a > 0.01 && opacityMult > 0.01) {
            vec3 N = computeNormal(uvw);
            float diff = max(dot(N, lightDir), 0.25);
            vec3 shaded = labelColor.rgb * (diff + 0.25);

            float alpha = labelColor.a * opacityMult * u_density * stepLength;
            accum.rgb += (1.0 - accum.a) * shaded * alpha;
            accum.a   += (1.0 - accum.a) * alpha;
          }
          continue;
        }
      }

      // --- Intensity-based fallback (unlabeled tissue) ---
      if (val > u_threshold) {
        float fallbackAlpha = 1.0;
        if (u_selectedLabel > 0.5) {
          fallbackAlpha = u_backgroundOpacity;
        }
        vec4 sampleCol = getTissueColor(val);
        if (sampleCol.a > 0.01 && fallbackAlpha > 0.01) {
          vec3 N = computeNormal(uvw);
          float diff = max(dot(N, lightDir), 0.25);
          vec3 shaded = sampleCol.rgb * (diff + 0.25);
          float alpha = sampleCol.a * fallbackAlpha * u_density * stepLength;
          accum.rgb += (1.0 - accum.a) * shaded * alpha;
          accum.a   += (1.0 - accum.a) * alpha;
        }
      }
    }
    if (accum.a <= 0.01) discard;
    fragColor = accum;
  }
`;

function VolumeMesh({ volumeData, dims, spacing, maskData, labelColormap, organToLabel }) {
  const meshRef = useRef();
  const lab3d = useStore((s) => s.lab3d);

  // CT volume texture
  const texture3D = useMemo(() => {
    if (!volumeData || !dims) return null;
    const [depth, height, width] = dims;
    const tex = new THREE.Data3DTexture(volumeData, width, height, depth);
    tex.format = THREE.RedFormat;
    tex.type = THREE.UnsignedByteType;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.wrapS = THREE.ClampToEdgeWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.wrapR = THREE.ClampToEdgeWrapping;
    tex.unpackAlignment = 1;
    tex.needsUpdate = true;
    return tex;
  }, [volumeData, dims]);

  // Segmentation mask texture (NearestFilter to preserve label IDs)
  const maskTexture = useMemo(() => {
    if (!maskData || !dims) return null;
    const [depth, height, width] = dims;
    const tex = new THREE.Data3DTexture(maskData, width, height, depth);
    tex.format = THREE.RedFormat;
    tex.type = THREE.UnsignedByteType;
    tex.minFilter = THREE.NearestFilter;
    tex.magFilter = THREE.NearestFilter;
    tex.wrapS = THREE.ClampToEdgeWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.wrapR = THREE.ClampToEdgeWrapping;
    tex.unpackAlignment = 1;
    tex.needsUpdate = true;
    return tex;
  }, [maskData, dims]);

  // 1D LUT texture (256x1 RGBA) from label colormap
  const lutTexture = useMemo(() => {
    const data = new Uint8Array(256 * 4);
    // Label 0 = transparent background
    data[0] = data[1] = data[2] = 0; data[3] = 0;

    const fallbackColors = [
      [230,180,120],[210,160,100],[190,150,90],[220,170,110],[200,155,95],
      [235,185,125],[195,145,85],[215,165,105],[205,158,98],[180,140,80],
      [180,120,90],[160,130,100],[170,140,110],[150,120,95],[140,110,85],[120,150,180],
      [220,40,40],[50,130,200],[180,50,50],[40,90,170],[240,30,30],
      [200,70,90],[190,50,70],[160,110,50],[200,40,40],[40,80,160],
      [60,120,190],[120,50,140],[210,80,100],[200,60,80],[190,40,50],
      [185,70,90],[70,110,160],[30,80,160],
      [160,80,180],[100,150,170],[140,200,120],[200,170,130],
      [80,170,220],[60,160,210],[40,150,200],
      [200,150,60],[180,40,70],[140,110,40],[80,160,60],
      [170,130,80],[200,170,70],[150,100,130],
      [200,60,60],[190,50,50],[210,70,70],[180,40,40],
      [195,55,55],[205,65,65],[185,45,45],[175,35,35],
      [165,30,30],[195,55,55],[185,45,45],[205,65,65],
      [195,55,55],[185,45,45],[175,35,35],[210,70,70],
      [200,60,60],[170,30,30],[190,50,50]
    ];

    for (let i = 1; i <= 255; i++) {
      const idx = i * 4;
      const rgb = labelColormap ? labelColormap[String(i)] : null;
      if (rgb) {
        data[idx]     = rgb[0];
        data[idx + 1] = rgb[1];
        data[idx + 2] = rgb[2];
        data[idx + 3] = 255;
      } else if (i - 1 < fallbackColors.length) {
        const c = fallbackColors[i - 1];
        data[idx] = c[0]; data[idx+1] = c[1]; data[idx+2] = c[2]; data[idx+3] = 255;
      } else {
        const c = fallbackColors[(i - 1) % fallbackColors.length];
        data[idx] = c[0]; data[idx+1] = c[1]; data[idx+2] = c[2]; data[idx+3] = 255;
      }
    }

    const tex = new THREE.DataTexture(data, 256, 1, THREE.RGBAFormat);
    tex.needsUpdate = true;
    return tex;
  }, [labelColormap]);

  const boxSize = useMemo(() => {
    if (!dims || !spacing) return new THREE.Vector3(1.5, 1.5, 1.5);
    const [depth, height, width] = dims;
    const spX = spacing[0] || 1;
    const spY = spacing[1] || 1;
    const spZ = spacing[2] || 1;
    const maxDim = Math.max(width * spX, height * spY, depth * spZ);
    return new THREE.Vector3(
      (width * spX) / maxDim * 1.8,
      (height * spY) / maxDim * 1.8,
      (depth * spZ) / maxDim * 1.8
    );
  }, [dims, spacing]);

  const uniforms = useMemo(() => ({
    u_data: { value: null },
    u_mask: { value: null },
    u_lut: { value: null },
    u_hasMask: { value: 0.0 },
    u_density: { value: 65.0 },
    u_threshold: { value: 0.12 },
    u_boxSize: { value: new THREE.Vector3(1, 1, 1) },
    u_clipEnabled: { value: new THREE.Vector3(0, 0, 0) },
    u_clipPos: { value: new THREE.Vector3(0.5, 0.5, 0.5) },
    u_clipFlipped: { value: new THREE.Vector3(0, 0, 0) },
    u_boxCrop: { value: 0.0 },
    u_selectedLabel: { value: 0.0 },
    u_organOpacity: { value: 1.0 },
    u_backgroundOpacity: { value: 1.0 },
  }), []);

  // Sync CT texture + box size
  useEffect(() => {
    if (texture3D) {
      uniforms.u_data.value = texture3D;
      uniforms.u_boxSize.value.copy(boxSize);
    }
  }, [texture3D, boxSize, uniforms]);

  // Sync mask + LUT textures
  useEffect(() => {
    if (maskTexture) {
      uniforms.u_mask.value = maskTexture;
      uniforms.u_hasMask.value = 1.0;
    } else {
      uniforms.u_mask.value = null;
      uniforms.u_hasMask.value = 0.0;
    }
    if (lutTexture) {
      uniforms.u_lut.value = lutTexture;
    }
  }, [maskTexture, lutTexture, uniforms]);

  // Sync lab3d controls to uniforms via useFrame (detects in-place .value mutations)
  useFrame(() => {
    uniforms.u_clipEnabled.value.set(
      lab3d.clipX.enabled ? 1.0 : 0.0,
      lab3d.clipY.enabled ? 1.0 : 0.0,
      lab3d.clipZ.enabled ? 1.0 : 0.0
    );
    uniforms.u_clipPos.value.set(
      lab3d.clipX.position,
      lab3d.clipY.position,
      lab3d.clipZ.position
    );
    uniforms.u_clipFlipped.value.set(
      lab3d.clipX.flipped ? 1.0 : 0.0,
      lab3d.clipY.flipped ? 1.0 : 0.0,
      lab3d.clipZ.flipped ? 1.0 : 0.0
    );
    uniforms.u_boxCrop.value = lab3d.boxCrop ? 1.0 : 0.0;
    uniforms.u_threshold.value = lab3d.tissueThreshold;

    const selectedLabel = (lab3d.selectedOrgan && organToLabel && organToLabel[lab3d.selectedOrgan])
      ? organToLabel[lab3d.selectedOrgan] : 0;
    uniforms.u_selectedLabel.value = selectedLabel;
    uniforms.u_organOpacity.value = lab3d.organOpacity;
    uniforms.u_backgroundOpacity.value = lab3d.backgroundOpacity;
  });

  return (
    <mesh ref={meshRef}>
      <boxGeometry args={[boxSize.x, boxSize.y, boxSize.z]} />
      <shaderMaterial
        glslVersion={THREE.GLSL3}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        side={THREE.BackSide}
        transparent={true}
        depthWrite={false}
      />
    </mesh>
  );
}

export default function VolumeRenderer() {
  const { volumeInfo } = useStore();
  const [volumeData, setVolumeData] = useState(null);
  const [maskData, setMaskData] = useState(null);
  const [labelColormap, setLabelColormap] = useState(null);
  const [organToLabel, setOrganToLabel] = useState(null);
  const [dims, setDims] = useState(null);
  const [spacing, setSpacing] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);

  useEffect(() => {
    let active = true;
    async function fetchVolume() {
      setIsLoading(true);
      setErrorMsg(null);
      try {
        const res = await getVolumeData();
        if (!active) return;
        if (!res?.data) throw new Error('No volume data returned from backend.');
        setDims(res.dims);
        setSpacing(res.spacing);

        // Decode CT volume
        const binary = atob(res.data);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        setVolumeData(bytes);

        // Decode segmentation mask
        if (res.mask) {
          const maskBin = atob(res.mask);
          const maskBytes = new Uint8Array(maskBin.length);
          for (let i = 0; i < maskBin.length; i++) maskBytes[i] = maskBin.charCodeAt(i);
          setMaskData(maskBytes);
        } else {
          setMaskData(null);
        }

        // Store label colormap
        setLabelColormap(res.label_colormap || {});

        // Store organ-to-label mapping
        setOrganToLabel(res.organ_to_label || {});

        setIsLoading(false);
      } catch (err) {
        console.error('Failed to load 3D volume texture:', err);
        if (active) { setErrorMsg(err.message || 'Error loading 3D volume'); setIsLoading(false); }
      }
    }
    fetchVolume();
    return () => { active = false; };
  }, [volumeInfo]);

  return (
    <div className="w-full h-full relative bg-[#040508]">
      {isLoading && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/60 backdrop-blur-xs text-cyan-400 text-xs gap-2">
          <div className="w-5 h-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
          <span>Generating 3D Volume...</span>
        </div>
      )}
      {errorMsg && (
        <div className="absolute inset-0 z-20 flex items-center justify-center text-rose-400 text-xs p-4 text-center">
          {errorMsg}
        </div>
      )}
      <Canvas
        camera={{ position: [0, 0, 2.4], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={1.0} />
        {volumeData && dims && (
          <VolumeMesh
            volumeData={volumeData}
            dims={dims}
            spacing={spacing}
            maskData={maskData}
            labelColormap={labelColormap}
            organToLabel={organToLabel}
          />
        )}
        <OrbitControls enableDamping dampingFactor={0.12} />
        <GizmoHelper alignment="bottom-right" margin={[60, 60]}>
          <GizmoViewport axisColors={['#ef4444', '#22c55e', '#3b82f6']} labelColor="#ffffff" />
        </GizmoHelper>
      </Canvas>
    </div>
  );
}
