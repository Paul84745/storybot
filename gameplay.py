"""Procedural 3D parkour gameplay footage (v2), rendered headless with OpenGL on the CPU.

A blocky runner sprints across a floating obby course: grassy platforms, balance
beams, hop blocks, stairs, jump pads that launch it into front flips through gold
rings, and checkpoint gates. It collects gems, kicks up dust, and the camera swings
and shakes like a real game. Sun lighting with real shadows, animated sky with
clouds (or stars), and an ocean or lava sea far below. Everything is generated, so
there are no copyright issues; every seed gives a new course and theme.

Writes OUT.mp4 plus OUT.mp4.hud.json (gem/checkpoint times for the HUD overlay).
Usage: python gameplay.py out.mp4 SECONDS [SEED]
"""
import json, math, os, random, subprocess, sys
import numpy as np
import moderngl

RW, RH = 720, 1280          # render size (upscaled to 1080x1920 when encoded)
FPS = 30
SPEED = 7.6                 # running speed, units per second
SEA_Y = -28.0
SHADOW = int(os.environ.get("GP_SHADOW", 2048))

# ---------------------------------------------------------------- themes
THEMES = [
    dict(name="sky islands", top=(0.20, 0.45, 0.92), hor=(0.72, 0.86, 1.0), suncol=(1.0, 0.96, 0.86), sky=(0.55, 0.7, 0.95),
         gnd=(0.35, 0.32, 0.28), side=(0.55, 0.38, 0.24), deep=(0.05, 0.28, 0.55), clouds=1.0,
         tops=[(0.36, 0.78, 0.30), (0.42, 0.82, 0.34), (0.98, 0.78, 0.25), (0.35, 0.62, 0.98), (0.98, 0.45, 0.45)],
         leaf=(0.25, 0.68, 0.25), trees=True),
    dict(name="sunset", top=(0.22, 0.16, 0.48), hor=(1.0, 0.58, 0.36), suncol=(1.0, 0.72, 0.5), sky=(0.75, 0.52, 0.6),
         gnd=(0.3, 0.2, 0.22), side=(0.48, 0.3, 0.28), deep=(0.18, 0.12, 0.3), clouds=0.85,
         tops=[(0.98, 0.6, 0.35), (0.96, 0.84, 0.42), (0.62, 0.46, 0.9), (0.4, 0.82, 0.78), (0.95, 0.42, 0.62)],
         leaf=(0.86, 0.45, 0.38), trees=True),
    dict(name="neon night", top=(0.01, 0.01, 0.05), hor=(0.10, 0.04, 0.22), suncol=(0.45, 0.45, 0.75), sky=(0.18, 0.15, 0.35),
         gnd=(0.05, 0.04, 0.1), side=(0.08, 0.08, 0.14), deep=(0.03, 0.02, 0.1), clouds=0.0, stars=1.0, neon=1.0,
         tops=[(0.1, 0.95, 0.95), (0.98, 0.2, 0.85), (0.45, 0.98, 0.3), (1.0, 0.85, 0.15), (0.35, 0.5, 1.0)],
         leaf=(0.9, 0.2, 0.9), trees=False),
    dict(name="lava", top=(0.16, 0.05, 0.06), hor=(0.85, 0.34, 0.12), suncol=(1.0, 0.62, 0.38), sky=(0.55, 0.3, 0.25),
         gnd=(0.5, 0.15, 0.05), side=(0.22, 0.2, 0.22), deep=(0.0, 0.0, 0.0), clouds=0.35, lava=1.0,
         tops=[(0.55, 0.55, 0.6), (0.95, 0.55, 0.15), (0.75, 0.75, 0.8), (0.9, 0.3, 0.15), (0.6, 0.5, 0.45)],
         leaf=(1.0, 0.5, 0.1), trees=False),
    dict(name="candy", top=(0.55, 0.62, 0.98), hor=(1.0, 0.82, 0.9), suncol=(1.0, 0.95, 0.92), sky=(0.85, 0.75, 0.95),
         gnd=(0.6, 0.45, 0.55), side=(0.95, 0.7, 0.8), deep=(0.35, 0.65, 0.85), clouds=1.0,
         tops=[(1.0, 0.6, 0.78), (0.6, 0.85, 1.0), (0.75, 0.95, 0.6), (1.0, 0.9, 0.55), (0.8, 0.65, 1.0)],
         leaf=(1.0, 0.55, 0.75), trees=True),
    dict(name="snow", top=(0.42, 0.62, 0.9), hor=(0.88, 0.94, 1.0), suncol=(1.0, 0.98, 0.95), sky=(0.7, 0.8, 0.95),
         gnd=(0.5, 0.55, 0.62), side=(0.45, 0.5, 0.6), deep=(0.1, 0.3, 0.45), clouds=0.9,
         tops=[(0.96, 0.97, 1.0), (0.7, 0.88, 1.0), (0.9, 0.95, 1.0), (0.55, 0.75, 0.95), (1.0, 0.75, 0.75)],
         leaf=(0.2, 0.45, 0.35), trees=True),
]
OUTFITS = [  # shirt, pants, cap, pack, shoes
    ((0.92, 0.22, 0.25), (0.18, 0.22, 0.42), (0.15, 0.15, 0.2), (0.98, 0.8, 0.2), (0.95, 0.95, 0.95)),
    ((0.2, 0.55, 0.98), (0.15, 0.15, 0.2), (0.98, 0.55, 0.1), (0.2, 0.2, 0.25), (0.98, 0.45, 0.1)),
    ((0.25, 0.8, 0.42), (0.3, 0.25, 0.2), (0.25, 0.8, 0.42), (0.55, 0.35, 0.2), (0.2, 0.2, 0.2)),
    ((0.98, 0.6, 0.1), (0.2, 0.3, 0.55), (0.98, 0.98, 0.98), (0.2, 0.55, 0.98), (0.98, 0.98, 0.98)),
    ((0.65, 0.35, 0.95), (0.12, 0.12, 0.16), (0.1, 0.95, 0.9), (0.98, 0.3, 0.7), (0.1, 0.95, 0.9)),
]
SKINS = [(0.98, 0.82, 0.68), (0.88, 0.66, 0.5), (0.66, 0.46, 0.32), (0.45, 0.3, 0.2)]

# ---------------------------------------------------------------- shaders
NOISE = """
float h2(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float h3(vec3 p){ return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float vnoise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(h2(i), h2(i+vec2(1,0)), f.x), mix(h2(i+vec2(0,1)), h2(i+vec2(1,1)), f.x), f.y); }
float fbm(vec2 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++){ s += a*vnoise(p); p = p*2.03 + 7.1; a *= 0.5; } return s; }
"""
VS = """
#version 330
in vec3 in_pos; in vec3 in_nrm; in mat4 i_model; in vec4 i_color;
uniform mat4 u_vp; uniform mat4 u_lvp;
out vec3 v_w; out vec3 v_n; out vec3 v_l; out vec3 v_sc; out vec4 v_c; out vec4 v_ls;
void main(){
  vec4 w = i_model * vec4(in_pos, 1.0);
  v_w = w.xyz; v_l = in_pos;
  v_sc = vec3(length(i_model[0].xyz), length(i_model[1].xyz), length(i_model[2].xyz));
  v_n = normalize(mat3(i_model) * (in_nrm / (v_sc * v_sc)));
  v_c = i_color; v_ls = u_lvp * w;
  gl_Position = u_vp * w;
}"""
FS = """
#version 330
in vec3 v_w; in vec3 v_n; in vec3 v_l; in vec3 v_sc; in vec4 v_c; in vec4 v_ls;
uniform vec3 u_cam, u_sun, u_suncol, u_sky, u_gnd, u_fog, u_side;
uniform float u_time, u_neon, u_fogd;
uniform sampler2DShadow u_shadow;
out vec4 f;
""" + NOISE + """
float shadow(float bias){
  vec3 p = v_ls.xyz / v_ls.w * 0.5 + 0.5;
  if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0) return 1.0;
  vec2 t = vec2(1.2 / 2048.0);
  float s = texture(u_shadow, vec3(p.xy + vec2(-t.x, -t.y), p.z - bias)) + texture(u_shadow, vec3(p.xy + vec2(t.x, -t.y), p.z - bias))
          + texture(u_shadow, vec3(p.xy + vec2(-t.x, t.y), p.z - bias)) + texture(u_shadow, vec3(p.xy + vec2(t.x, t.y), p.z - bias));
  return s * 0.25;
}
void main(){
  vec3 n = normalize(v_n);
  vec3 v = normalize(u_cam - v_w);
  float mat = floor(v_c.a + 0.001);
  float seed = fract(v_c.a);
  vec3 alb = v_c.rgb, emis = vec3(0.0);
  if (mat > 0.5 && mat < 1.5) {                       // terrain block
    vec3 p = (v_l + 0.5) * v_sc;                       // position in block units inside this box
    float nz = h3(floor(p - n * 0.01) + seed * 97.0);
    vec3 sidec = mix(alb * 0.5, u_side, 0.6);
    float fromTop = (0.5 - v_l.y) * v_sc.y;
    if (n.y > 0.5) alb *= 0.9 + 0.18 * nz;
    else if (n.y < -0.5) alb = sidec * 0.65;
    else {
      float along = abs(n.x) > 0.5 ? p.z : p.x;
      float jag = 0.16 + 0.12 * h2(vec2(floor(along * 3.0), seed * 53.0));
      alb = fromTop < jag ? alb * (0.88 + 0.12 * nz) : sidec * (0.85 + 0.25 * nz);
    }
    vec3 g = abs(fract(p - n * 0.01) - 0.5);
    float e = abs(n.y) > 0.5 ? max(g.x, g.z) : (abs(n.x) > 0.5 ? max(g.y, g.z) : max(g.x, g.y));
    alb *= mix(1.0, 0.8, smoothstep(0.455, 0.495, e));
    vec3 b = min(p, v_sc - p);                         // distance to the box's outer edges
    float edge = min(min(abs(n.x) > 0.5 ? 9.0 : b.x, abs(n.y) > 0.5 ? 9.0 : b.y), abs(n.z) > 0.5 ? 9.0 : b.z);
    alb = mix(alb, alb * 1.25 + 0.04, 1.0 - smoothstep(0.0, 0.07, edge));
    if (u_neon > 0.5) {
      emis = v_c.rgb * (smoothstep(0.43, 0.49, e) * 0.9 + (1.0 - smoothstep(0.0, 0.09, edge)) * 1.8);
      alb = vec3(0.06, 0.06, 0.1) + alb * 0.08;
    }
  } else if (mat > 1.5 && mat < 2.5) {                // glowing: gems, pads, rings
    emis = alb * (0.75 + 0.25 * sin(u_time * 6.0 + v_w.z * 0.7));
    alb *= 0.55;
  }
  float diff = max(dot(n, u_sun), 0.0);
  float sh = diff > 0.0 ? shadow(0.0008 + 0.002 * (1.0 - diff)) : 0.0;
  vec3 hemi = mix(u_gnd, u_sky, n.y * 0.5 + 0.5);
  vec3 c = alb * (hemi * 0.7 + u_suncol * diff * (0.25 + 0.85 * sh));
  c += pow(1.0 - max(dot(n, v), 0.0), 3.0) * 0.14 * u_sky;
  c += emis;
  float d = length(v_w - u_cam);
  float fog = 1.0 - exp(-pow(d * u_fogd, 2.0));
  fog = max(fog, smoothstep(-6.0, -30.0, v_w.y) * 0.6);   // haze towards the sea
  f = vec4(mix(c, u_fog, clamp(fog, 0.0, 1.0)), 1.0);
}"""
SKY_VS = "#version 330\nin vec2 p; out vec2 v_ndc; void main(){ v_ndc = p; gl_Position = vec4(p, 0.99999, 1.0); }"
SKY_FS = """
#version 330
in vec2 v_ndc;
uniform mat4 u_ivp; uniform vec3 u_top, u_hor, u_sun, u_suncol; uniform float u_time, u_stars, u_clouds;
out vec4 f;
""" + NOISE + """
void main(){
  vec4 w = u_ivp * vec4(v_ndc, 1.0, 1.0);
  vec3 d = normalize(w.xyz / w.w);
  float y = d.y;
  vec3 c = mix(u_hor, u_top, smoothstep(-0.02, 0.55, y));
  float sd = max(dot(d, u_sun), 0.0);
  c += u_suncol * (pow(sd, 700.0) * 2.5 + pow(sd, 10.0) * 0.28);
  if (u_stars > 0.5 && y > 0.0) {
    vec2 g = floor(d.xz / (y + 0.25) * 140.0);
    c += vec3(step(0.9965, h2(g)) * (0.6 + 0.4 * sin(u_time * 3.0 + h2(g + 3.0) * 30.0))) * smoothstep(0.0, 0.35, y);
  }
  if (u_clouds > 0.0 && y > 0.01) {
    vec2 uv = d.xz / y * 0.32 + vec2(u_time * 0.012, u_time * 0.005);
    float n = fbm(uv * 1.7);
    float cl = smoothstep(0.48, 0.78, n) * smoothstep(0.01, 0.22, y);
    vec3 cc = mix(u_hor, vec3(1.0), 0.7) + u_suncol * 0.08;
    c = mix(c, cc * (0.85 + 0.25 * n), cl * 0.9 * u_clouds);
  }
  f = vec4(c, 1.0);
}"""
SEA_VS = """
#version 330
in vec2 p; uniform mat4 u_vp; uniform vec2 u_off; uniform float u_y; out vec3 v_w;
void main(){ v_w = vec3(p.x * 600.0 + u_off.x, u_y, p.y * 600.0 + u_off.y); gl_Position = u_vp * vec4(v_w, 1.0); }"""
SEA_FS = """
#version 330
in vec3 v_w;
uniform vec3 u_cam, u_sun, u_suncol, u_fog, u_top, u_hor, u_deep; uniform float u_time, u_lava, u_fogd;
out vec4 f;
""" + NOISE + """
void main(){
  vec2 p = v_w.xz; float t = u_time; vec3 c;
  if (u_lava > 0.5) {
    float n = fbm(p * 0.05 + vec2(t * 0.03, t * 0.02));
    float n2 = fbm(p * 0.18 - vec2(t * 0.06, -t * 0.04));
    c = mix(vec3(0.3, 0.03, 0.0), vec3(1.0, 0.42, 0.04), smoothstep(0.35, 0.75, n));
    c += vec3(1.0, 0.85, 0.35) * smoothstep(0.6, 0.72, n2) * 0.9;
  } else {
    vec2 g = vec2(0.0);
    g += vec2(0.8, 0.6) * cos(dot(p, vec2(0.8, 0.6)) * 0.35 + t * 1.3) * 0.045;
    g += vec2(-0.5, 0.85) * cos(dot(p, vec2(-0.5, 0.85)) * 0.6 + t * 1.7) * 0.04;
    g += vec2(0.95, -0.3) * cos(dot(p, vec2(0.95, -0.3)) * 1.3 + t * 2.3) * 0.035;
    g += (vec2(vnoise(p * 0.7 + t * 0.3), vnoise(p * 0.7 - t * 0.3 + 9.0)) - 0.5) * 0.12;
    vec3 n = normalize(vec3(-g.x, 1.0, -g.y));
    vec3 v = normalize(u_cam - v_w);
    float fr = 0.03 + 0.97 * pow(1.0 - max(dot(n, v), 0.0), 5.0);
    vec3 r = reflect(-v, n);
    vec3 sky = mix(u_hor, u_top, smoothstep(0.0, 0.6, r.y));
    c = mix(u_deep, sky, fr);
    c += u_suncol * pow(max(dot(r, u_sun), 0.0), 160.0) * 1.6;
  }
  float d = length(v_w - u_cam);
  float fog = 1.0 - exp(-pow(d * u_fogd * 0.8, 2.0));
  f = vec4(mix(c, u_fog, clamp(fog, 0.0, 1.0)), 1.0);
}"""
SH_VS = "#version 330\nin vec3 in_pos; in mat4 i_model; uniform mat4 u_lvp; void main(){ gl_Position = u_lvp * i_model * vec4(in_pos, 1.0); }"
SH_FS = "#version 330\nvoid main(){}"


# ---------------------------------------------------------------- math helpers
def T(x, y, z):
    m = np.identity(4, "f4"); m[:3, 3] = (x, y, z); return m


def S(x, y, z):
    return np.diag([x, y, z, 1.0]).astype("f4")


def RX(a):
    c, s = math.cos(a), math.sin(a); m = np.identity(4, "f4")
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c; return m


def RY(a):
    c, s = math.cos(a), math.sin(a); m = np.identity(4, "f4")
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c; return m


def RZ(a):
    c, s = math.cos(a), math.sin(a); m = np.identity(4, "f4")
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c; return m


def box(x, y, z, sx, sy, sz):
    return T(x, y, z) @ S(sx, sy, sz)


def persp(fov, aspect, near, far):
    f = 1 / math.tan(math.radians(fov) / 2)
    return np.array([[f / aspect, 0, 0, 0], [0, f, 0, 0],
                     [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]], "f4")


def ortho(r, near, far):
    return np.array([[1 / r, 0, 0, 0], [0, 1 / r, 0, 0],
                     [0, 0, -2 / (far - near), -(far + near) / (far - near)], [0, 0, 0, 1]], "f4")


def look_at(eye, target, up=(0, 1, 0)):
    eye, target, up = (np.asarray(v, "f4") for v in (eye, target, up))
    z = eye - target; z /= np.linalg.norm(z)
    x = np.cross(up, z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    m = np.identity(4, "f4")
    m[0, :3], m[1, :3], m[2, :3] = x, y, z
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def cube():
    v = []
    faces = [((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
             ((-1, 0, 0), [(-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1)]),
             ((0, 1, 0), [(-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)]),
             ((0, -1, 0), [(-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1)]),
             ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
             ((0, 0, -1), [(1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)])]
    for n, q in faces:
        for i in (0, 1, 2, 0, 2, 3):
            v += [c * 0.5 for c in q[i]] + list(n)
    return np.array(v, dtype="f4")


def smooth(a, b, t):
    t = max(0.0, min(1.0, (t - a) / (b - a)))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- course
class Course:
    """A winding obby: curves left and right, zig-zags, spiral tower climbs, drops and launch pads.

    Each surface is an oriented box (center, heading). The runner runs along a surface's heading and
    jumps between surfaces on parabolic arcs; all timing is precomputed so pose(t) is cheap.
    """

    def __init__(self, rng, th, seconds):
        self.rng, self.th = rng, th
        self.surfs, self.blocks, self.gems, self.segs = [], [], [], []
        self.checkpoints, self.rings = [], []
        self.build_surfaces(seconds + 6)
        self.build_path()
        self.build_blocks()

    @staticmethod
    def fwd(h):
        return np.array([math.sin(h), 0.0, math.cos(h)], "f4")

    @staticmethod
    def right(h):
        return np.array([math.cos(h), 0.0, -math.sin(h)], "f4")

    def add(self, center, h, length, w, kind):
        s = dict(c=np.array(center, "f4"), h=h, L=length, w=w, kind=kind)
        self.surfs.append(s)
        return s

    def edge(self, s):
        """Point at the far edge of a surface, on its top."""
        return s["c"] + self.fwd(s["h"]) * (s["L"] / 2)

    def place(self, prev, gap, dh, dy, length, w, kind, lateral=0.0):
        """Next surface after `prev`: jump `gap` along the bend, turn by dh, rise dy, shift sideways."""
        h = prev["h"] + dh
        hj = prev["h"] + dh / 2
        c = self.edge(prev) + self.fwd(hj) * gap + self.fwd(h) * (length / 2) + self.right(h) * lateral
        c[1] = max(-8.0, min(20.0, float(prev["c"][1]) + dy))
        return self.add(c, h, length, w, kind)

    def build_surfaces(self, seconds):
        rng = self.rng
        cur = self.add((0, 0, 0), 0.0, 14, 4, "start")
        est, since_cp = 0.0, 0
        bend, bend_left = 0.0, 0          # current curve: heading change per surface, surfaces remaining
        base_h = 0.0                      # the course's overall direction; curves swing around it
        while est < seconds:
            y = float(cur["c"][1])
            if bend_left <= 0:
                target = base_h + rng.uniform(-1.6, 1.6)
                diff = math.atan2(math.sin(target - cur["h"]), math.cos(target - cur["h"]))
                bend_left = rng.randint(3, 6)
                bend = diff / bend_left
            since_cp += 1
            weights = dict(spiral=0.08, zig=0.13, drop=0.08, pad=0.11, beam=0.1, stairs=0.09, hops=0.11, normal=0.3)
            if y > 9:                     # high up: favour ways down
                weights.update(spiral=0.0, stairs=0.0, drop=0.3, pad=0.2)
            elif y < -2:                  # low: favour climbs
                weights.update(drop=0.0, spiral=0.16, stairs=0.18)
            sec = rng.choices(list(weights), list(weights.values()))[0]
            if since_cp >= 14:
                since_cp = 0
                cur = self.place(cur, rng.uniform(2.2, 3.0), bend, 0, 7, 5, "checkpoint"); est += 1.5
            elif sec == "spiral":         # spiral tower climb: one full loop of hop blocks going up
                d = rng.choice([-1, 1])
                n = 10
                for _ in range(n):
                    cur = self.place(cur, 1.25, d * 2 * math.pi / n, 0.8, 1.4, 1.4, "spiral"); est += 0.5
                cur = self.place(cur, 2.2, 0.0, 0, 5, 3, "normal"); est += 1.0
            elif sec == "zig":            # zig-zag: diagonal jumps left and right
                side = rng.choice([-1, 1])
                for _ in range(rng.randint(4, 6)):
                    cur = self.place(cur, 1.6, bend * 0.3, rng.choice([0, 0, 1, -1]), 1.6, 1.6, "zig", lateral=side * 2.4)
                    side = -side; est += 0.6
            elif sec == "drop":           # big drop down
                cur = self.place(cur, rng.uniform(2.5, 3.5), bend, -rng.uniform(3.5, 6.0), rng.uniform(5, 7), 4, "land"); est += 1.4
            elif sec == "pad":            # jump pad -> super jump up or down, with a sharp turn
                cur = self.place(cur, rng.uniform(2.0, 3.0), bend, 0, rng.uniform(4, 6), 3, "pad"); est += 0.9
                dy = rng.choice([-6, -4, -3] if y > 6 else ([3, 5, 7] if y < 0 else [-4, -3, 3, 5]))
                cur = self.place(cur, rng.uniform(9.0, 12.0), rng.uniform(-0.9, 0.9), dy, rng.uniform(5, 7), 4, "land"); est += 2.2
            elif sec == "beam":           # balance beam on a curve
                cur = self.place(cur, rng.uniform(2.0, 3.0), bend, rng.choice([0, 1]), rng.uniform(6, 9), 0.7, "beam"); est += 1.4
            elif sec == "stairs":         # stairs up, curving
                for _ in range(rng.randint(3, 5)):
                    cur = self.place(cur, 1.2, bend * 0.5, 1.0, 1.6, 2, "stair"); est += 0.45
            elif sec == "hops":           # hop blocks
                for _ in range(rng.randint(3, 5)):
                    cur = self.place(cur, rng.uniform(1.6, 2.3), bend * 0.5 + rng.uniform(-0.35, 0.35), rng.choice([0, 0, 1, -1, -1]),
                                     1, 1, "hop", lateral=rng.uniform(-0.8, 0.8)); est += 0.5
            else:                         # normal platform
                cur = self.place(cur, rng.uniform(2.2, 3.2), bend, rng.choice([-2, -1, 0, 0, 1, 2]), rng.uniform(3, 7),
                                 rng.choice([2, 3, 3, 4]), "normal"); est += 1.1
            bend_left -= 1
            if rng.random() < 0.08:       # slowly change the overall direction too
                base_h += rng.uniform(-0.8, 0.8)

    def build_path(self):
        rng, t, prev = self.rng, 0.0, None
        for s in self.surfs:
            f = self.fwd(s["h"])
            half = max(0.0, s["L"] / 2 - 0.35)
            a, b = s["c"] - f * half, s["c"] + f * half
            if prev is not None:
                d = a - prev[0]
                horiz = math.hypot(float(d[0]), float(d[2]))
                if prev[1] == "pad":
                    h, dur, kind = 5.5 + 0.12 * horiz + max(0.0, float(d[1])), 1.3 + 0.02 * horiz, "super"
                else:
                    h, dur, kind = 0.8 + 0.2 * horiz + max(0.0, float(d[1])), max(0.42, horiz / (SPEED * 1.08) + 0.12), "jump"
                    if d[1] < -2:         # big drops take a little longer and arc less
                        h, dur = 0.9, dur + 0.25
                self.segs.append(dict(kind=kind, t0=t, dur=dur, a=prev[0], b=a, h=h))
                apex = (prev[0] + a) / 2 + np.array([0, h, 0], "f4")
                if kind == "super":
                    self.rings.append((apex + np.array([0, 1.0, 0], "f4"), math.atan2(float(d[0]), float(d[2]))))
                elif horiz > 2.4 and rng.random() < 0.3:
                    self.gems.append(apex + np.array([0, 1.0, 0], "f4"))
                t += dur
            L = float(np.linalg.norm(b - a))
            self.segs.append(dict(kind="run", t0=t, dur=max(L / SPEED, 0.04), a=a, b=b, h=0, surf=s))
            if s["kind"] == "checkpoint":
                self.checkpoints.append(t + (L / 2) / SPEED)
            if s["kind"] in ("normal", "land", "beam", "checkpoint") and L > 3 and rng.random() < 0.65:
                for k in (-1.3, 0, 1.3):
                    self.gems.append(s["c"] + f * k + np.array([0, 1.0, 0], "f4"))
            if s["kind"] in ("spiral", "zig") and rng.random() < 0.5:
                self.gems.append(s["c"] + np.array([0, 1.0, 0], "f4"))
            t += max(L / SPEED, 0.04)
            prev = (b, s["kind"])
        self.total = t

    def pose(self, t, hint=0):
        i = hint
        while i < len(self.segs) - 1 and t > self.segs[i]["t0"] + self.segs[i]["dur"]:
            i += 1
        sg = self.segs[i]
        s = max(0.0, min(1.0, (t - sg["t0"]) / sg["dur"]))
        p = sg["a"] + (sg["b"] - sg["a"]) * s
        if sg["kind"] != "run":
            p = p + np.array([0, sg["h"] * 4 * s * (1 - s), 0], "f4")
        return p, sg, s, i

    def clear_of_course(self, p, dist):
        p = np.asarray(p, "f4")
        return all(float(np.sum((s["c"][[0, 2]] - p[[0, 2]]) ** 2)) > dist * dist or abs(float(s["c"][1] - p[1])) > dist
                   for s in self.surfs)

    def build_blocks(self):
        rng, th, B = self.rng, self.th, self.blocks
        tops = th["tops"]
        seed = lambda: rng.uniform(0.0, 0.9)
        for i, s in enumerate(self.surfs):
            c, h, L, w, k = s["c"], s["h"], s["L"], s["w"], s["kind"]
            M0 = T(*c) @ RY(h)
            top = tops[0] if k in ("start", "land", "checkpoint") and th.get("trees") else rng.choice(tops)
            if k == "beam":
                B.append((M0 @ box(0, -0.3, 0, w, 0.6, L), (0.72, 0.52, 0.32, 1 + seed())))
                for zz in (-L / 2 + 0.3, L / 2 - 0.3):
                    B.append((M0 @ box(0, -2.2, zz, 0.5, 3.4, 0.5), (*th["side"], 1 + seed())))
                continue
            thick = 2.0 if k in ("start", "checkpoint", "land") else (0.8 if k in ("hop", "zig", "spiral") else 1.0)
            B.append((M0 @ box(0, -thick / 2, 0, w, thick, L), (*top, 1 + seed())))
            if (k == "spiral" and i % 2 == 0) or (k not in ("hop", "stair", "zig", "spiral") and rng.random() < 0.35):
                ph = float(c[1]) - thick - SEA_Y + 2
                pw = 0.6 if k == "spiral" else min(w, 1.5)
                B.append((M0 @ box(0, -thick - ph / 2, 0, pw, ph, min(L, pw)), (*th["side"], 1 + seed())))
            if k == "pad":
                B.append((M0 @ box(0, 0.07, L / 2 - 0.9, 1.6, 0.14, 1.3), (0.15, 0.95, 1.0, 2)))
                for j in range(3):
                    B.append((M0 @ box(0, 0.16, L / 2 - 1.3 + j * 0.4, 0.5, 0.06, 0.16), (1, 1, 1, 2)))
            if k == "checkpoint":
                for sx in (-1, 1):
                    x = sx * (w / 2 - 0.35)
                    B.append((M0 @ box(x, 2.3, 0, 0.5, 4.6, 0.5), (0.95, 0.95, 0.98, 0)))
                    B.append((M0 @ box(x, 5.4, 0, 0.12, 1.4, 0.12), (0.3, 0.3, 0.3, 0)))
                    B.append((M0 @ box(x + 0.4, 5.85, 0, 0.7, 0.45, 0.06), (0.2, 0.95, 0.4, 2)))
                B.append((M0 @ box(0, 4.75, 0, w, 0.5, 0.5), (0.95, 0.95, 0.98, 0)))
                B.append((M0 @ box(0, 4.42, 0, w - 0.8, 0.16, 0.3), (0.2, 0.95, 0.4, 2)))
        # floating scenery islands, kept clear of the course
        for s in self.surfs[::2]:
            for _ in range(2):
                if rng.random() > 0.75:
                    continue
                side = rng.choice([-1, 1])
                p = s["c"] + self.right(s["h"]) * side * rng.uniform(14, 34) + self.fwd(s["h"]) * rng.uniform(-6, 6)
                p[1] += rng.uniform(-9, 3)
                if not self.clear_of_course(p, 10):
                    continue
                sw, sd, sh = round(rng.uniform(3, 8)), round(rng.uniform(3, 8)), rng.uniform(2, 4)
                Mi = T(*p) @ RY(rng.uniform(0, 3.14))
                B.append((Mi @ box(0, -sh / 2, 0, sw, sh, sd), (*rng.choice(tops), 1 + seed())))
                B.append((Mi @ box(0, -sh - 1.2, 0, max(1, sw - 2), 2.4, max(1, sd - 2)), (*th["side"], 1 + seed())))
                for _ in range(rng.randint(1, 3)):
                    q = Mi @ np.array([rng.uniform(-sw / 3, sw / 3), 0, rng.uniform(-sd / 3, sd / 3), 1], "f4")
                    if th.get("trees"):
                        self.tree(q[0], q[1], q[2], rng.uniform(0.9, 1.4))
                    else:
                        hh = rng.uniform(1.5, 4)
                        B.append((box(q[0], q[1] + hh / 2, q[2], 0.5, hh, 0.5), (*th["leaf"], 2)))
        # far-away towers for a skyline
        for s in self.surfs[::5]:
            for side in (-1, 1):
                if rng.random() < 0.6:
                    p = s["c"] + self.right(s["h"]) * side * rng.uniform(55, 120)
                    if not self.clear_of_course(p, 30):
                        continue
                    wd, hh = rng.uniform(8, 18), rng.uniform(25, 70)
                    B.append((box(p[0], SEA_Y + hh / 2 - 2, p[2], wd, hh, wd), (*rng.choice(tops), 1 + seed())))
        for c, yaw in self.rings:                           # gold rings on super jumps
            for j in range(16):
                a = j / 16 * 2 * math.pi
                M = T(*c) @ RY(yaw) @ RZ(a) @ T(1.9, 0, 0) @ S(0.32, 0.8, 0.32)
                B.append((M, (1.0, 0.8, 0.15, 2)))

    def tree(self, x, y, z, k):
        th, B, rng = self.th, self.blocks, self.rng
        B.append((box(x, y + 1.1 * k, z, 0.5 * k, 2.2 * k, 0.5 * k), (0.45, 0.3, 0.18, 0)))
        B.append((box(x, y + 2.9 * k, z, 2.2 * k, 1.8 * k, 2.2 * k), (*th["leaf"], 1 + rng.uniform(0, 0.9))))
        B.append((box(x, y + 4.0 * k, z, 1.3 * k, 0.9 * k, 1.3 * k),
                  (*np.clip(np.array(th["leaf"]) * 1.15, 0, 1), 1 + rng.uniform(0, 0.9))))


# ---------------------------------------------------------------- particles
class Particles:
    def __init__(self, rng):
        self.rng, self.items = rng, []

    def burst(self, pos, n, color, speed, up, life, size, mat=0, grav=-6.0):
        r = self.rng
        for _ in range(n):
            a, e = r.uniform(0, 2 * math.pi), r.uniform(-0.2, 1.0)
            v = np.array([math.cos(a) * speed * r.uniform(0.5, 1), up * r.uniform(0.5, 1.2) + e * speed * 0.3,
                          math.sin(a) * speed * r.uniform(0.5, 1)], "f4")
            self.items.append([np.array(pos, "f4") + 0, v, life, life, size * r.uniform(0.7, 1.2), color, mat, grav, r.uniform(0, 6)])

    def step(self, dt):
        for it in self.items:
            it[1][1] += it[7] * dt
            it[0] += it[1] * dt
            it[2] -= dt
        self.items = [it for it in self.items if it[2] > 0]

    def instances(self, t):
        out = []
        for p, v, life, life0, size, col, mat, g, spin in self.items:
            k = size * (life / life0) ** 0.7
            out.append((T(*p) @ RY(spin + t * 4) @ RX(spin * 0.7) @ S(k, k, k), (*col, mat)))
        return out


# ---------------------------------------------------------------- runner
def runner_parts(p, yaw, pose, outfit, skin, squash):
    shirt, pants, cap, pack, shoes = outfit
    B = T(*p) @ RY(yaw)
    if squash > 0:
        B = B @ S(1 + squash * 0.6, 1 - squash, 1 + squash * 0.6)
    H = B @ T(0, 0.98 + pose["bob"], 0)
    if pose["flip"]:
        H = H @ T(0, 0.45, 0) @ RX(pose["flip"]) @ T(0, -0.45, 0)
    U = H @ RX(pose["lean"])
    parts = [
        (U @ box(0, 0.42, 0, 0.64, 0.74, 0.38), shirt),
        (U @ box(0, 1.08, 0.02, 0.56, 0.56, 0.56), skin),
        (U @ box(0, 1.39, -0.01, 0.6, 0.14, 0.6), cap),
        (U @ box(0, 1.33, 0.3, 0.52, 0.06, 0.26), cap),
        (U @ box(0.13, 1.1, 0.29, 0.09, 0.12, 0.02), (0.08, 0.08, 0.1)),
        (U @ box(-0.13, 1.1, 0.29, 0.09, 0.12, 0.02), (0.08, 0.08, 0.1)),
        (U @ box(0, 0.48, -0.27, 0.46, 0.52, 0.2), pack),
    ]
    for side in (1, -1):
        arm = pose["armL"] if side > 0 else pose["armR"]
        A = U @ T(side * 0.44, 0.74, 0) @ RX(arm) @ RZ(side * pose["spread"])
        parts.append((A @ box(0, -0.3, 0, 0.2, 0.62, 0.22), shirt))
        parts.append((A @ box(0, -0.66, 0, 0.19, 0.14, 0.21), skin))
        leg = pose["legL"] if side > 0 else pose["legR"]
        Lg = H @ T(side * 0.17, 0.0, 0) @ RX(leg)
        parts.append((Lg @ box(0, -0.43, 0, 0.25, 0.84, 0.28), pants))
        parts.append((Lg @ box(0, -0.9, 0.05, 0.28, 0.15, 0.38), shoes))
    return [(m, (*c, 0)) for m, c in parts]


# ---------------------------------------------------------------- render
def render(out, seconds, seed=None, theme=None):
    seed = random.randrange(10**6) if seed is None else seed
    rng = random.Random(seed)
    th = rng.choice(THEMES)
    if theme:
        th = next(x for x in THEMES if x["name"] == theme)
    outfit, skin = rng.choice(OUTFITS), rng.choice(SKINS)
    sun = np.array([rng.uniform(-0.55, 0.55), 0.78, rng.uniform(0.2, 0.6)], "f4"); sun /= np.linalg.norm(sun)
    course = Course(rng, th, seconds)
    parts_fx = Particles(rng)

    ctx = moderngl.create_context(standalone=True, backend="egl")
    prog = ctx.program(vertex_shader=VS, fragment_shader=FS)
    sprog = ctx.program(vertex_shader=SH_VS, fragment_shader=SH_FS)
    sky = ctx.program(vertex_shader=SKY_VS, fragment_shader=SKY_FS)
    sea = ctx.program(vertex_shader=SEA_VS, fragment_shader=SEA_FS)
    quad = ctx.buffer(np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], "f4"))
    sky_vao = ctx.vertex_array(sky, [(quad, "2f", "p")])
    sea_vao = ctx.vertex_array(sea, [(quad, "2f", "p")])
    vbo = ctx.buffer(cube())

    def inst(items):
        return np.array([np.concatenate([m.T.flatten(), np.array(c, "f4")]) for m, c in items], "f4")

    static_buf = ctx.buffer(inst(course.blocks))
    dyn_buf = ctx.buffer(reserve=80 * 400)
    vaos = {}
    for name, buf in (("static", static_buf), ("dyn", dyn_buf)):
        vaos[name] = ctx.vertex_array(prog, [(vbo, "3f 3f", "in_pos", "in_nrm"), (buf, "16f 4f/i", "i_model", "i_color")])
        vaos[name + "_sh"] = ctx.vertex_array(sprog, [(vbo, "3f 12x", "in_pos"), (buf, "16f 16x/i", "i_model")])

    shadow_tex = ctx.depth_texture((SHADOW, SHADOW))
    shadow_tex.compare_func = "<="
    shadow_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    shadow_fbo = ctx.framebuffer(depth_attachment=shadow_tex)
    MS = int(os.environ.get("GP_MSAA", 4))
    fbo = ctx.framebuffer(ctx.renderbuffer((RW, RH), samples=MS), ctx.depth_renderbuffer((RW, RH), samples=MS))
    out_fbo = ctx.framebuffer(ctx.renderbuffer((RW, RH)))

    fogd = 1 / 125.0
    prog["u_sun"].value = tuple(sun); prog["u_suncol"].value = th["suncol"]
    prog["u_sky"].value = th["sky"]; prog["u_gnd"].value = th["gnd"]; prog["u_fog"].value = th["hor"]
    prog["u_side"].value = th["side"]; prog["u_neon"].value = th.get("neon", 0.0); prog["u_fogd"].value = fogd
    prog["u_shadow"].value = 0
    for k, v in (("u_top", th["top"]), ("u_hor", th["hor"]), ("u_sun", tuple(sun)), ("u_suncol", th["suncol"])):
        sky[k].value = v
    sky["u_stars"].value = th.get("stars", 0.0); sky["u_clouds"].value = th.get("clouds", 0.0)
    for k, v in (("u_sun", tuple(sun)), ("u_suncol", th["suncol"]), ("u_fog", th["hor"]), ("u_top", th["top"]),
                 ("u_hor", th["hor"]), ("u_deep", th["deep"])):
        sea[k].value = v
    sea["u_lava"].value = th.get("lava", 0.0); sea["u_fogd"].value = fogd; sea["u_y"].value = SEA_Y

    ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{RW}x{RH}", "-r", str(FPS), "-i", "-", "-vf", "vflip,scale=1080:1920:flags=lanczos",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out],
                          stdin=subprocess.PIPE)

    dt = 1 / FPS
    gems = [g.copy() for g in course.gems]
    gem_times, cp_times = [], []
    cps = list(course.checkpoints)
    pose = dict(legL=0.0, legR=0.0, armL=0.0, armR=0.0, spread=0.1, lean=0.15, bob=0.0, flip=0.0)
    cam = tgt = None
    heading = 0.0
    yaw_s = 0.0
    sup_s = 0.0
    shake = 0.0
    last_kind, land_t, run_dist, puff_t = "run", -9.0, 0.0, 0.0
    hint = 0
    frames = int(seconds * FPS)
    for fi in range(frames):
        t = fi * dt
        p, sg, s, hint = course.pose(t, hint)
        kind = sg["kind"]
        d = sg["b"] - sg["a"]
        yaw = math.atan2(float(d[0]), float(d[2])) if abs(d[0]) + abs(d[2]) > 1e-3 else yaw_s
        yaw_s += math.atan2(math.sin(yaw - yaw_s), math.cos(yaw - yaw_s)) * 0.3

        # events: take-off, landing
        if kind != last_kind:
            if kind == "run" and last_kind in ("jump", "super"):
                big = last_kind == "super"
                land_t = t
                parts_fx.burst(p + np.array([0, 0.1, 0], "f4"), 18 if big else 9, (0.92, 0.9, 0.86), 3.2 if big else 2.2,
                               1.2, 0.5, 0.26 if big else 0.2, 0, -4.0)
                shake = max(shake, 0.35 if big else 0.12)
            if kind == "super":
                parts_fx.burst(p + np.array([0, 0.2, 0], "f4"), 16, (0.2, 0.95, 1.0), 2.5, 5.0, 0.6, 0.22, 2, -9.0)
            last_kind = kind

        # animation pose targets
        if kind == "run":
            run_dist += SPEED * dt
            ph = run_dist * 1.5
            sw = math.sin(ph) * 0.9
            tgt_pose = dict(legL=-sw, legR=sw, armL=sw * 0.85, armR=-sw * 0.85, spread=0.12, lean=0.2,
                            bob=0.07 * abs(math.cos(ph)), flip=0.0)
            puff_t -= dt
            if puff_t <= 0:
                puff_t = 0.22
                parts_fx.burst(p + np.array([0, 0.05, 0], "f4"), 2, (0.9, 0.88, 0.84), 0.6, 0.6, 0.3, 0.12, 0, -1.0)
        elif kind == "jump":
            tgt_pose = dict(legL=-1.0, legR=-0.25, armL=-2.3, armR=-1.2, spread=0.35, lean=0.08, bob=0.0, flip=0.0)
        else:  # super jump with a front flip
            fl = 2 * math.pi * smooth(0.18, 0.78, s)
            tuck = math.sin(math.pi * smooth(0.12, 0.85, s))
            tgt_pose = dict(legL=-1.5 * tuck, legR=-1.5 * tuck, armL=-0.6 - 1.6 * (1 - tuck), armR=-0.6 - 1.6 * (1 - tuck),
                            spread=0.25 + 0.9 * (1 - tuck), lean=0.1, bob=0.0, flip=fl)
            for _ in range(2):
                parts_fx.burst(p + np.array([0, 0.9, 0], "f4"), 1, outfit[3], 0.3, 0.0, 0.35, 0.22, 2, 0.0)
        for k2 in pose:
            if k2 == "flip":
                pose[k2] = tgt_pose[k2]
            else:
                pose[k2] += (tgt_pose[k2] - pose[k2]) * 0.38

        # gems and checkpoints
        center = p + np.array([0, 0.9, 0], "f4")
        keep = []
        for g in gems:
            if float(np.sum((g - center) ** 2)) < 1.25:
                gem_times.append(round(t, 2))
                parts_fx.burst(g, 12, (1.0, 0.85, 0.2), 3.5, 2.0, 0.55, 0.16, 2, -7.0)
            else:
                keep.append(g)
        gems = keep
        while cps and t >= cps[0]:
            cp_times.append(round(cps.pop(0), 2))
            parts_fx.burst(p + np.array([0, 3.5, 0], "f4"), 24, (0.25, 1.0, 0.45), 4.0, 3.0, 0.8, 0.2, 2, -6.0)
        parts_fx.step(dt)

        # build dynamic instances
        squash = 0.17 * math.exp(-(t - land_t) * 14) if t - land_t < 0.35 else 0.0
        dyn = runner_parts(p, yaw_s, pose, outfit, skin, squash)
        for g in gems:
            if -4 < g[2] - p[2] < 110:
                dyn.append((T(g[0], g[1] + 0.15 * math.sin(t * 3 + g[2]), g[2]) @ RY(t * 2.5 + g[2]) @ RX(0.62) @ RZ(0.62)
                            @ S(0.42, 0.42, 0.42), (1.0, 0.82, 0.15, 2)))
        dyn += parts_fx.instances(t)
        dyn = dyn[:400]
        dyn_buf.write(inst(dyn))

        # camera
        ahead, _, _, _ = course.pose(t + 0.7, hint)
        dv = ahead - p
        if abs(dv[0]) + abs(dv[2]) > 0.3:
            want_h = math.atan2(float(dv[0]), float(dv[2]))
            heading += math.atan2(math.sin(want_h - heading), math.cos(want_h - heading)) * 0.05
        sup_s += ((1.0 if kind == "super" else 0.0) - sup_s) * 0.06
        fwd = np.array([math.sin(heading), 0, math.cos(heading)], "f4")
        right = np.array([math.cos(heading), 0, -math.sin(heading)], "f4")
        lateral = 1.6 * math.sin(t * 0.23) + 0.8 * math.sin(t * 0.07 + 1.3)
        back, up = 6.4 + 2.4 * sup_s, 3.4 + 0.4 * sup_s
        want = p + right * lateral * (1 + 0.8 * sup_s) - fwd * back + np.array([0, up, 0], "f4")
        look = p + np.array([0, 2.3 + 0.6 * sup_s, 0], "f4") + fwd * 4.2
        cam = want if cam is None else cam + (want - cam) * np.array([0.12, 0.1 + 0.08 * sup_s, 0.12], "f4")
        tgt = look if tgt is None else tgt + (look - tgt) * (0.2 + 0.15 * sup_s)
        shake *= math.exp(-10 * dt)
        jitter = np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), 0], "f4") * shake
        view = look_at(cam + jitter, tgt + jitter * 0.5)
        fov = 70 + 10 * sup_s
        proj = persp(fov, RW / RH, 0.1, 320)
        vp = proj @ view

        # shadow pass
        lc = p + fwd * 10
        lvp = ortho(44, 1, 220) @ look_at(lc + sun * 100, lc)
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        shadow_fbo.use(); shadow_fbo.clear(depth=1.0)
        ctx.cull_face = "front"
        sprog["u_lvp"].write(lvp.T.copy().tobytes())
        vaos["static_sh"].render(instances=len(course.blocks))
        vaos["dyn_sh"].render(instances=len(dyn))
        ctx.cull_face = "back"

        # main pass: opaque blocks first, then sea and sky only where nothing covers them
        fbo.use(); fbo.clear(*th["hor"], 1.0)
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        prog["u_vp"].write(vp.T.copy().tobytes()); prog["u_lvp"].write(lvp.T.copy().tobytes())
        prog["u_cam"].value = tuple(cam); prog["u_time"].value = t
        shadow_tex.use(0)
        vaos["dyn"].render(instances=len(dyn))
        vaos["static"].render(instances=len(course.blocks))
        ctx.disable(moderngl.CULL_FACE)
        sea["u_vp"].write(vp.T.copy().tobytes()); sea["u_cam"].value = tuple(cam)
        sea["u_off"].value = (float(cam[0]), float(cam[2])); sea["u_time"].value = t
        sea_vao.render()
        rot_only = view.copy(); rot_only[:3, 3] = 0
        sky["u_ivp"].write(np.linalg.inv(proj @ rot_only).T.astype("f4").copy().tobytes())
        sky["u_time"].value = t
        sky_vao.render()
        ctx.copy_framebuffer(out_fbo, fbo)
        ff.stdin.write(out_fbo.read(components=3))
    ff.stdin.close(); ff.wait()
    json.dump({"theme": th["name"], "gems": gem_times, "checkpoints": cp_times}, open(out + ".hud.json", "w"))
    return out


if __name__ == "__main__":
    render(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else None,
           sys.argv[4] if len(sys.argv) > 4 else None)
