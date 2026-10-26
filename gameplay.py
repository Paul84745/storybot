"""Procedural 3D parkour 'gameplay' footage, rendered headless with OpenGL (CPU is fine).

A blocky character runs and jumps across floating block platforms, collecting
spinning gems, with a third-person follow camera. Everything is generated, so
there are no copyright issues. Each seed gives a different course and theme.

Usage: python gameplay.py out.mp4 SECONDS [SEED]
"""
import math, random, subprocess, sys
import numpy as np
import moderngl

RW, RH = 720, 1280      # render size (upscaled to 1080x1920 when encoded)
FPS = 30

THEMES = [  # sky top, sky bottom, fog, sun dir, platform palette
    dict(top=(0.30, 0.55, 0.95), bot=(0.75, 0.88, 1.0), pal=[(0.42, 0.78, 0.35), (0.95, 0.75, 0.3), (0.35, 0.65, 0.95), (0.95, 0.45, 0.45), (0.75, 0.5, 0.95)]),
    dict(top=(0.35, 0.18, 0.55), bot=(1.0, 0.6, 0.4), pal=[(0.98, 0.55, 0.35), (0.95, 0.85, 0.45), (0.55, 0.4, 0.85), (0.35, 0.8, 0.8), (0.95, 0.4, 0.65)]),
    dict(top=(0.03, 0.03, 0.12), bot=(0.15, 0.08, 0.3), pal=[(0.1, 0.95, 0.9), (0.95, 0.2, 0.85), (0.4, 0.95, 0.3), (1.0, 0.85, 0.2), (0.35, 0.5, 1.0)]),
    dict(top=(0.45, 0.75, 0.85), bot=(0.9, 0.97, 0.95), pal=[(0.95, 0.95, 1.0), (0.55, 0.85, 0.95), (0.4, 0.6, 0.9), (0.85, 0.75, 0.95), (0.6, 0.9, 0.8)]),
]

VS = """
#version 330
in vec3 in_pos; in vec3 in_nrm;
in mat4 i_model; in vec4 i_color;
uniform mat4 u_vp;
out vec3 v_wpos; out vec3 v_nrm; out vec4 v_col; out vec3 v_lpos; out vec3 v_scale;
void main(){
  vec4 w = i_model * vec4(in_pos,1.0);
  v_wpos = w.xyz; v_lpos = in_pos;
  v_scale = vec3(length(i_model[0].xyz), length(i_model[1].xyz), length(i_model[2].xyz));
  v_nrm = normalize(mat3(i_model) * in_nrm);
  v_col = i_color;
  gl_Position = u_vp * w;
}"""
FS = """
#version 330
in vec3 v_wpos; in vec3 v_nrm; in vec4 v_col; in vec3 v_lpos; in vec3 v_scale;
uniform vec3 u_cam; uniform vec3 u_fog; uniform vec3 u_sun; uniform float u_glow;
out vec4 f;
void main(){
  vec3 n = normalize(v_nrm);
  float diff = max(dot(n, u_sun), 0.0);
  vec3 c = v_col.rgb * (0.48 + 0.62 * diff);
  if (v_col.a > 0.5) {                     // block grid lines (Minecraft-like)
    vec3 p = (v_lpos + 0.5) * v_scale;      // local position in block units
    vec3 g = abs(fract(p) - 0.5);
    float e = 0.5;
    if (abs(n.x) > 0.5) e = max(g.y, g.z); else if (abs(n.y) > 0.5) e = max(g.x, g.z); else e = max(g.x, g.y);
    c *= mix(1.0, 0.78, smoothstep(0.455, 0.49, e));
    vec3 b = min((v_lpos + 0.5) * v_scale, (0.5 - v_lpos) * v_scale);   // outer edge highlight
    float edge = min(min(abs(n.x)>0.5?9.:b.x, abs(n.y)>0.5?9.:b.y), abs(n.z)>0.5?9.:b.z);
    c = mix(c, c * 1.25 + 0.05, 1.0 - smoothstep(0.0, 0.06, edge));
  }
  c += v_col.rgb * u_glow * 0.35;
  float d = length(v_wpos - u_cam);
  float fog = 1.0 - exp(-pow(d / 70.0, 2.0));
  f = vec4(mix(c, u_fog, fog), 1.0);
}"""
SKY_VS = "#version 330\nin vec2 p; out float y; void main(){ y = p.y*0.5+0.5; gl_Position = vec4(p,0.999,1.0);}"
SKY_FS = """#version 330
in float y; uniform vec3 top; uniform vec3 bot; out vec4 f;
void main(){ f = vec4(mix(bot, top, smoothstep(0.0, 1.0, y)), 1.0); }"""


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


def persp(fov, aspect, near, far):
    f = 1 / math.tan(math.radians(fov) / 2)
    return np.array([[f / aspect, 0, 0, 0], [0, f, 0, 0],
                     [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]], "f4")


def look_at(eye, target, up=(0, 1, 0)):
    eye, target, up = map(np.asarray, (eye, target, up))
    z = eye - target; z = z / np.linalg.norm(z)
    x = np.cross(up, z); x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    m = np.identity(4, "f4")
    m[0, :3], m[1, :3], m[2, :3] = x, y, z
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def trs(t, s, ry=0.0, rx=0.0):
    cy, sy, cx, sx = math.cos(ry), math.sin(ry), math.cos(rx), math.sin(rx)
    R = np.array([[cy, sy * sx, sy * cx], [0, cx, -sx], [-sy, cy * sx, cy * cx]], "f4")
    m = np.identity(4, "f4")
    m[:3, :3] = R * np.asarray(s, "f4")
    m[:3, 3] = t
    return m


class Course:
    def __init__(self, rng, length):
        self.plats = []   # (cx, top_y, z0, z1, width)
        z, x, y = 0.0, 0.0, 0.0
        self.plats.append((0.0, 0.0, -6.0, 6.0, 4.0))
        z = 6.0
        while z < length:
            kind = rng.random()
            gap = rng.uniform(1.8, 3.6)
            dz = 1.0 if kind < 0.3 else rng.uniform(2.0, 6.0)          # single-block jumps sometimes
            wdt = 1.0 if kind < 0.3 else rng.choice([1.0, 2.0, 3.0])
            x = max(-6, min(6, x + rng.uniform(-2.2, 2.2)))
            y = max(-4, min(6, y + rng.choice([-1, 0, 0, 1, 1])))
            self.plats.append((round(x), float(y), z + gap, z + gap + dz, wdt))
            z += gap + dz
        # character path: segments of (t-length) running or jumping
        self.speed = 7.5

    def pose(self, dist):
        """Character position, facing angle and phase info for a distance along the run."""
        segs = self.segments()
        for kind, a, b, L, extra in segs:
            if dist <= L:
                s = dist / L if L else 1
                p = a + (b - a) * s
                if kind == "jump":
                    p[1] += extra * 4 * s * (1 - s)
                return p, b - a, kind, s
            dist -= L
        a, b = segs[-1][1], segs[-1][2]
        return b.copy(), b - a, "run", 1.0

    def segments(self):
        if hasattr(self, "_segs"):
            return self._segs
        segs = []
        prev = None
        for (cx, ty, z0, z1, w) in self.plats:
            start = np.array([cx, ty, z0 + 0.4], "f4"); end = np.array([cx, ty, z1 - 0.4], "f4")
            if prev is not None:
                d = start - prev
                horiz = math.hypot(d[0], d[2])
                segs.append(("jump", prev, start, horiz, 1.1 + 0.25 * horiz + max(0, d[1])))
            segs.append(("run", start, end, float(np.linalg.norm(end - start)), 0))
            prev = end
        self._segs = segs
        return segs


def render(out, seconds, seed=None):
    seed = random.randrange(10**6) if seed is None else seed
    rng = random.Random(seed)
    th = rng.choice(THEMES)
    sun = np.array([rng.uniform(-0.6, 0.6), 0.85, 0.45], "f4"); sun /= np.linalg.norm(sun)
    course = Course(rng, 7.5 * seconds * 1.35 + 40)

    ctx = moderngl.create_context(standalone=True, backend="egl")
    ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
    prog = ctx.program(vertex_shader=VS, fragment_shader=FS)
    sky = ctx.program(vertex_shader=SKY_VS, fragment_shader=SKY_FS)
    vbo = ctx.buffer(cube())
    sky_vao = ctx.vertex_array(sky, [(ctx.buffer(np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], "f4")), "2f", "p")])
    sky["top"].value, sky["bot"].value = th["top"], th["bot"]
    fbo = ctx.framebuffer(ctx.renderbuffer((RW, RH), samples=4), ctx.depth_renderbuffer((RW, RH), samples=4))
    out_fbo = ctx.framebuffer(ctx.renderbuffer((RW, RH)))
    prog["u_fog"].value = tuple(np.array(th["bot"]) * 0.9 + 0.1 * np.array(th["top"]))
    prog["u_sun"].value = tuple(sun)
    prog["u_glow"].value = 0.6 if th is THEMES[2] else 0.0

    # static instances: platforms (+ pillars) and distant scenery
    static = []
    for i, (cx, ty, z0, z1, w) in enumerate(course.plats):
        col = th["pal"][i % len(th["pal"])]
        dz = z1 - z0
        static.append((trs((cx, ty - 0.5, (z0 + z1) / 2), (w, 1, dz)), (*col, 1)))
        if rng.random() < 0.35:   # pillar underneath
            static.append((trs((cx, ty - 4, (z0 + z1) / 2), (min(w, 1), 6, 1)), (*np.array(col) * 0.7, 1)))
    for _ in range(int(len(course.plats) * 1.2)):  # floating scenery islands
        zc = rng.uniform(-10, course.plats[-1][3])
        side = rng.choice([-1, 1])
        sz = rng.uniform(2, 7)
        col = np.array(rng.choice(th["pal"])) * 0.85
        static.append((trs((side * rng.uniform(16, 45), rng.uniform(-22, 8), zc), (sz, sz * rng.uniform(0.4, 1.2), sz)), (*(col * 0.8 + 0.2 * np.array(th['bot'])), 1)))
    gems = [((cx, ty + 1.1, (z0 + z1) / 2)) for (cx, ty, z0, z1, w) in course.plats[1:] if rng.random() < 0.55]

    def inst_array(items):
        return np.array([np.concatenate([m.T.flatten(), np.array(c, "f4")]) for m, c in items], "f4")

    static_buf = ctx.buffer(inst_array(static))
    static_vao = ctx.vertex_array(prog, [(vbo, "3f 3f", "in_pos", "in_nrm"), (static_buf, "16f 4f/i", "i_model", "i_color")])
    dyn_buf = ctx.buffer(reserve=64 * 80 * 4)
    dyn_vao = ctx.vertex_array(prog, [(vbo, "3f 3f", "in_pos", "in_nrm"), (dyn_buf, "16f 4f/i", "i_model", "i_color")])

    proj = persp(68, RW / RH, 0.1, 220)
    shirt = np.array(rng.choice([(0.9, 0.2, 0.25), (0.2, 0.5, 0.95), (0.2, 0.75, 0.4), (0.95, 0.6, 0.1)]), "f4")
    cam = None
    ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{RW}x{RH}", "-r", str(FPS), "-i", "-", "-vf", "vflip,scale=1080:1920:flags=lanczos",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out],
                          stdin=subprocess.PIPE)
    frames = int(seconds * FPS)
    for fi in range(frames):
        t = fi / FPS
        p, d, kind, s = course.pose(course.speed * t)
        yaw = math.atan2(d[0], d[2])
        # character (blocky): legs/arms swing while running, tuck while jumping
        sw = math.sin(t * 12) * (0.9 if kind == "run" else 0.25)
        tuck = 0.9 if kind == "jump" else 0
        dyn = []
        def part(off, size, col, rx=0.0, pivot=0.0):
            o = np.array(off, "f4")
            cy, sy = math.cos(yaw), math.sin(yaw)
            # rotate around a hip/shoulder pivot then place in world
            local = np.array([o[0], o[1] - pivot * math.cos(rx) + pivot, o[2] + pivot * math.sin(rx)], "f4")
            world = p + np.array([cy * local[0] + sy * local[2], local[1], -sy * local[0] + cy * local[2]], "f4")
            dyn.append((trs(world, size, yaw, rx), (*col, 0)))
        skin, pants = (0.95, 0.78, 0.62), (0.2, 0.25, 0.45)
        part((0, 1.25, 0), (0.55, 0.65, 0.32), shirt)                           # torso
        part((0, 1.83, 0), (0.48, 0.48, 0.48), skin)                            # head
        part((0.14, 0.45, 0), (0.24, 0.65, 0.26), pants, sw - tuck, 0.32)       # legs
        part((-0.14, 0.45, 0), (0.24, 0.65, 0.26), pants, -sw - tuck, 0.32)
        part((0.4, 1.25, 0), (0.2, 0.62, 0.22), shirt, -sw * 0.9 - tuck * 1.6, 0.3)  # arms
        part((-0.4, 1.25, 0), (0.2, 0.62, 0.22), shirt, sw * 0.9 - tuck * 1.6, 0.3)
        # blob shadow on the platform below
        ground = None
        for (cx, ty, z0, z1, w) in course.plats:
            if z0 - 0.3 <= p[2] <= z1 + 0.3 and abs(p[0] - cx) <= w / 2 + 0.3:
                ground = ty
        if ground is not None and p[1] >= ground - 0.01:
            k = max(0.35, 1 - (p[1] - ground) / 4)
            dyn.append((trs((p[0], ground + 0.01, p[2]), (0.65 * k, 0.01, 0.65 * k)), (0.12, 0.12, 0.16, 0)))
        for g in gems:   # spinning gems vanish once collected
            if g[2] > p[2] - 0.3 and g[2] - p[2] < 90:
                bob = 0.15 * math.sin(t * 3 + g[2])
                dyn.append((trs((g[0], g[1] + bob, g[2]), (0.35, 0.35, 0.35), t * 2.5 + g[2], 0.6), (1.0, 0.85, 0.15, 0)))
        dyn_buf.write(inst_array(dyn))

        target = p + np.array([0, 1.2, 0], "f4") + np.array([math.sin(yaw), 0, math.cos(yaw)], "f4") * 3.5
        want = p + np.array([-math.sin(yaw) * 5.5, 3.4, -math.cos(yaw) * 5.5], "f4")
        cam = want if cam is None else cam + (want - cam) * 0.12
        fov = 68 + (6 * math.sin(math.pi * s) if kind == "jump" else 0)
        vp = persp(fov, RW / RH, 0.1, 220) @ look_at(cam, target)
        prog["u_vp"].write(vp.T.copy().tobytes())
        prog["u_cam"].value = tuple(cam)

        fbo.use(); fbo.clear(*th["bot"], 1.0)
        ctx.disable(moderngl.DEPTH_TEST); sky_vao.render(); ctx.enable(moderngl.DEPTH_TEST)
        static_vao.render(instances=len(static))
        dyn_vao.render(instances=len(dyn))
        ctx.copy_framebuffer(out_fbo, fbo)
        ff.stdin.write(out_fbo.read(components=3))
    ff.stdin.close(); ff.wait()
    return out


if __name__ == "__main__":
    render(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else None)
