# Multi-Label Segmentation 3D Rendering — Implementation Plan

## Overview

Replace the single-intensity transfer function with a dual-mode renderer:
1. **Multi-label mode** (when mask exists): Each organ gets a distinct RGBA color from a LUT texture
2. **Intensity-only fallback** (when no mask): Current `getTissueColor()` behavior preserved

Skin/outer tissue appears semi-transparent by modulating alpha with CT intensity — low-density voxels (skin/fat ~30-70 HU) are naturally more transparent, while dense structures (bone, organs) are solid.

---

## Current Architecture

| Component | What it does now |
|-----------|-----------------|
| `GET /api/volume/data` | Returns `{data, mask, dims, spacing}` — mask is base64 uint8 but frontend **ignores it** |
| `VolumeRenderer.jsx` | Creates one `Data3DTexture` from CT data only |
| Fragment shader | Hardcoded `getTissueColor(float val)` — purely intensity-based, no label awareness |
| Store `lab3d` | Has `selectedOrgan`, `organOpacity`, `backgroundOpacity` — unused by shader |

## Changes Required

### 1. Backend — `backend/main.py`

**Add `label_colormap` to `/api/volume/data` response** (line ~225):

```python
return {
    "data": vol_b64,
    "mask": mask_b64,
    "dims": dims,
    "spacing": list(vol["spacing"]),
    "label_colormap": {str(k): list(v) for k, v in vol.get("label_colormap", {}).items()},
}
```

The `label_colormap` is already populated during segmentation (`vol["label_colormap"][label_idx] = COLORMAP[...]`). Just need to expose it.

### 2. Frontend — `frontend/src/components/VolumeRenderer.jsx`

#### 2a. Decode mask from API response (VolumeRenderer component, ~line 252-260)

```javascript
const res = await getVolumeData();
// ... existing code ...
setVolumeData(bytes);

// NEW: decode mask
if (res.mask) {
  const maskBin = atob(res.mask);
  const maskBytes = new Uint8Array(maskBin.length);
  for (let i = 0; i < maskBin.length; i++) maskBytes[i] = maskBin.charCodeAt(i);
  setMaskData(maskBytes);
} else {
  setMaskData(null);
}

// NEW: store colormap
setLabelColormap(res.label_colormap || {});
```

#### 2b. Create mask texture (VolumeMesh component, new useMemo)

```javascript
const maskTexture = useMemo(() => {
  if (!maskData || !dims) return null;
  const [depth, height, width] = dims;
  const tex = new THREE.Data3DTexture(maskData, width, height, depth);
  tex.format = THREE.RedFormat;
  tex.type = THREE.UnsignedByteType;
  tex.minFilter = THREE.NearestFilter;  // Nearest — no interpolation for labels
  tex.magFilter = THREE.NearestFilter;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.wrapR = THREE.ClampToEdgeWrapping;
  tex.unpackAlignment = 1;
  tex.needsUpdate = true;
  return tex;
}, [maskData, dims]);
```

**Key**: `NearestFilter` (not `LinearFilter`) — label IDs must not be interpolated.

#### 2c. Create LUT texture (new useMemo, from labelColormap)

Build a 256×1 RGBA `DataTexture` from the colormap:

```javascript
const lutTexture = useMemo(() => {
  const data = new Uint8Array(256 * 4);  // 256 RGBA pixels
  // Label 0 = transparent background
  data[0] = data[1] = data[2] = 0; data[3] = 0;

  for (let i = 1; i <= 255; i++) {
    const rgb = labelColormap[String(i)];
    const idx = i * 4;
    if (rgb) {
      data[idx]     = rgb[0];
      data[idx + 1] = rgb[1];
      data[idx + 2] = rgb[2];
      data[idx + 3] = 255;  // Full opacity — modulated in shader by CT intensity
    } else {
      // Fallback: cycle through default colors
      const defaults = [
        [239,68,68], [34,197,94], [59,130,246], [245,158,11],
        [168,85,247], [236,72,153], [20,184,166], [249,115,22],
        [14,165,233], [132,204,22]
      ];
      const c = defaults[(i - 1) % defaults.length];
      data[idx] = c[0]; data[idx+1] = c[1]; data[idx+2] = c[2]; data[idx+3] = 255;
    }
  }

  const tex = new THREE.DataTexture(data, 256, 1, THREE.RGBAFormat);
  tex.needsUpdate = true;
  return tex;
}, [labelColormap]);
```

#### 2d. Update uniforms

Add three new uniforms:

```javascript
const uniforms = useMemo(() => ({
  // ... existing uniforms ...
  u_mask:        { value: null },
  u_lut:         { value: null },
  u_hasMask:     { value: 0.0 },
}), []);
```

Sync in useEffect:

```javascript
useEffect(() => {
  if (maskTexture) {
    uniforms.u_mask.value = maskTexture;
    uniforms.u_hasMask.value = 1.0;
  } else {
    uniforms.u_hasMask.value = 0.0;
  }
  if (lutTexture) {
    uniforms.u_lut.value = lutTexture;
  }
}, [maskTexture, lutTexture, uniforms]);
```

#### 2e. Updated GLSL Fragment Shader

```glsl
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

// Existing intensity-based fallback (unchanged)
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

    // --- Multi-label path (when mask is available) ---
    if (u_hasMask > 0.5) {
      float label = texture(u_mask, uvw).r * 255.0;

      if (label > 0.5) {
        // Look up organ color from LUT
        vec2 lutUV = vec2((label + 0.5) / 256.0, 0.5);
        vec4 labelColor = texture(u_lut, lutUV);

        // Semi-transparent skin: modulate alpha by CT intensity
        // Low-density voxels (skin/fat) → more transparent
        // High-density voxels (bone/organs) → solid
        float intensityFactor = clamp((val - u_threshold) / 0.3, 0.0, 1.0);

        if (labelColor.a > 0.01 && intensityFactor > 0.01) {
          // Compute normal from CT intensity gradients (not mask)
          vec3 eps = vec3(0.006);
          float gx = texture(u_data, uvw + vec3(eps.x,0,0)).r - texture(u_data, uvw - vec3(eps.x,0,0)).r;
          float gy = texture(u_data, uvw + vec3(0,eps.y,0)).r - texture(u_data, uvw - vec3(0,eps.y,0)).r;
          float gz = texture(u_data, uvw + vec3(0,0,eps.z)).r - texture(u_data, uvw - vec3(0,0,eps.z)).r;
          vec3 N = -normalize(vec3(gx, gy, gz) + 0.0001);
          float diff = max(dot(N, lightDir), 0.25);
          vec3 shaded = labelColor.rgb * (diff + 0.25);

          float alpha = labelColor.a * intensityFactor * u_density * stepLength;
          accum.rgb += (1.0 - accum.a) * shaded * alpha;
          accum.a   += (1.0 - accum.a) * alpha;
        }
        continue;  // Skip intensity-based path for labeled voxels
      }
    }

    // --- Intensity-based fallback (no mask or unlabeled voxel) ---
    if (val > u_threshold) {
      vec4 sampleCol = getTissueColor(val);
      if (sampleCol.a > 0.01) {
        vec3 eps = vec3(0.006);
        float gx = texture(u_data, uvw + vec3(eps.x,0,0)).r - texture(u_data, uvw - vec3(eps.x,0,0)).r;
        float gy = texture(u_data, uvw + vec3(0,eps.y,0)).r - texture(u_data, uvw - vec3(0,eps.y,0)).r;
        float gz = texture(u_data, uvw + vec3(0,0,eps.z)).r - texture(u_data, uvw - vec3(0,0,eps.z)).r;
        vec3 N = -normalize(vec3(gx, gy, gz) + 0.0001);
        float diff = max(dot(N, lightDir), 0.25);
        vec3 shaded = sampleCol.rgb * (diff + 0.25);
        float alpha = sampleCol.a * u_density * stepLength;
        accum.rgb += (1.0 - accum.a) * shaded * alpha;
        accum.a   += (1.0 - accum.a) * alpha;
      }
    }
  }
  if (accum.a <= 0.01) discard;
  fragColor = accum;
}
```

### 3. Store — No changes needed

The `lab3d.organOpacity` and `lab3d.backgroundOpacity` sliders are already wired in the sidebar but not connected to the shader. They could be used to scale the LUT alpha values, but for v1 the LUT alpha alone provides the semi-transparent skin effect.

---

## Semi-Transparent Skin — How It Works

The key line in the shader:
```glsl
float intensityFactor = clamp((val - u_threshold) / 0.3, 0.0, 1.0);
```

This maps CT intensity to an opacity multiplier:
- **Below threshold** → 0.0 (fully transparent)
- **Threshold to threshold+0.3** → 0.0–1.0 (gradient ramp)
- **Above threshold+0.3** → 1.0 (fully opaque)

Since skin/fat has low CT values (~30-70 HU, normalized ~0.05-0.12), it falls in the gradient zone and appears semi-transparent. Dense structures (bone, contrast-enhanced organs) have high CT values and render solid.

The `tissueThreshold` slider in the 3D Lab sidebar already controls `u_threshold`, giving the user interactive control over how much skin is visible.

---

## File Changes Summary

| File | Change |
|------|--------|
| `backend/main.py` | Add `label_colormap` to `/api/volume/data` response |
| `frontend/src/components/VolumeRenderer.jsx` | Decode mask, create mask+LUT textures, update shader + uniforms |

---

## Testing

1. Load a CT volume without running segmentation → should render identically to current behavior (intensity-only)
2. Run AI segmentation → 3D view should show labeled organs with distinct colors
3. Verify skin/fat appears semi-transparent, bones/organs are solid
4. Adjust `tissueThreshold` slider → skin visibility changes
5. Toggle clip planes → labels should clip correctly alongside CT data
6. No segmentation available (TotalSegmentator missing) → fallback segmenter produces labeled masks → should render with LUT colors
