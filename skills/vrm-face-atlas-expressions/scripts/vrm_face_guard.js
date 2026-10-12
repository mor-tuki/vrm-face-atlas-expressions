// vrm_face_guard.js — runtime guard for atlas-switched VRM 1.0 faces (tested with @pixiv/three-vrm v3.4.x).
//
// Texture-transform offsets ADD UP in VRM. With an emotion-row x vowel-column mouth atlas that is exactly what we
// want for ONE emotion + ONE vowel, but two vowels (or two emotions) at the same time jump to a wrong cell.
// Lip-sync engines often blend two visemes during a transition, so clamp before handing values to three-vrm.
//
// Usage:
//   import { FaceGuard } from './vrm_face_guard.js';
//   const face = new FaceGuard(vrm);
//   face.setEmotion('happy');                 // or null
//   face.setVisemes({ aa: 0.7, ih: 0.4 });    // raw lip-sync output; only the strongest one >= 0.5 is kept
//   // in your render loop:
//   face.update(delta);                       // applies values + idle blinking
//   vrm.update(delta);

const VOWELS = ['aa', 'ih', 'ou', 'ee', 'oh'];
const EMOTIONS = ['happy', 'angry', 'sad', 'surprised', 'relaxed'];

export class FaceGuard {
  constructor(vrm, opts = {}) {
    this.em = vrm.expressionManager;
    this.emotion = null;
    this.visemes = {};
    this.blinkTimer = 0;
    this.nextBlink = this._rand(opts.blinkMin ?? 2.0, opts.blinkMax ?? 5.5);
    this.blinkDur = opts.blinkDuration ?? 0.12;     // seconds the eyes stay closed (binary expressions)
    this.blinking = 0;
  }
  _rand(a, b) { return a + Math.random() * (b - a); }

  setEmotion(name) { this.emotion = EMOTIONS.includes(name) ? name : null; }
  setVisemes(v) { this.visemes = v || {}; }

  update(dt) {
    const em = this.em;
    if (!em) return;
    // 1) one emotion at most
    for (const e of EMOTIONS) em.setValue(e, e === this.emotion ? 1 : 0);
    // 2) one vowel at most: keep the strongest, and only if it is clearly on (binary binds switch at 0.5)
    let best = null, bestV = 0;
    for (const v of VOWELS) { const x = this.visemes[v] || 0; if (x > bestV) { best = v; bestV = x; } }
    for (const v of VOWELS) em.setValue(v, v === best && bestV >= 0.5 ? 1 : 0);
    // 3) idle blink — skipped while an emotion owns the eye tiles (emotions use overrideBlink = block anyway)
    if (this.emotion) { em.setValue('blink', 0); this.blinking = 0; this.blinkTimer = 0; return; }
    if (this.blinking > 0) {
      this.blinking -= dt;
      em.setValue('blink', this.blinking > 0 ? 1 : 0);
      return;
    }
    this.blinkTimer += dt;
    if (this.blinkTimer >= this.nextBlink) {
      this.blinkTimer = 0; this.nextBlink = this._rand(2.0, 5.5); this.blinking = this.blinkDur;
      if (Math.random() < 0.15) this.nextBlink = 0.18;   // occasional double blink
      em.setValue('blink', 1);
    } else {
      em.setValue('blink', 0);
    }
  }
}

// Head-follow helper: when a "look at camera" head turn is used, fade it out as the camera goes behind the
// avatar instead of clamping at +-180 deg (clamping makes the head snap when the camera crosses the back).
//   const w = lookAtWeight(angleBetweenFacingAndCameraRad);  headYaw = targetYaw * w;
export function lookAtWeight(angleRad, fullDeg = 60, zeroDeg = 120) {
  const a = Math.abs(angleRad) * 180 / Math.PI;
  const t = Math.min(1, Math.max(0, (a - fullDeg) / (zeroDeg - fullDeg)));
  return 1 - t * t * (3 - 2 * t);   // smoothstep: 1 in front, 0 behind
}
