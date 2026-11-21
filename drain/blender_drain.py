"""Construction-stage RCC storm drain scene. Run: blender -b -P blender_drain.py -- out.png"""
import bpy, sys, math, random, os
STAGE = int(os.environ.get('STAGE', '0'))   # 0 = composite view, 1-8 = construction step
from mathutils import Vector

random.seed(4)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "//drain_render.png"

# ---------- dimensions (m) ----------
L, TW, TD = 10.0, 2.0, 1.5          # trench length, width, depth
GRAV = 0.15                          # gravel sub-base
WALL, BASE = 0.20, 0.20              # wall + base slab thickness
OUTW = 1.6                           # drain outer width (0.2 working space each side)
TOP = -0.10                          # top of drain walls
Z0 = -TD + GRAV                      # underside of base slab
CAST_END, POUR_START, BAR_END = 6.0, 6.0, 8.6   # cured | active pour | exposed bars

# ---------- helpers ----------
def box(name, size, loc, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object; o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        m = o.modifiers.new("bev", "BEVEL"); m.width = bevel; m.segments = 2
    o.data.materials.append(mat)
    return o

def bar(a, b, r, mat, coll):
    a, b = Vector(a), Vector(b); d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=r, depth=d.length, location=(a + b) / 2)
    o = bpy.context.object
    o.rotation_mode = "QUATERNION"; o.rotation_quaternion = d.to_track_quat("Z", "Y")
    o.data.materials.append(mat); coll.append(o)

def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join(); objs[0].name = name
    return objs[0]

def node_mat(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes["Principled BSDF"]
    return m, nt, bsdf

def tex_coord(nt):
    return nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]

def noise(nt, scale, detail=8, rough=0.6, co=None):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale; n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    if co: nt.links.new(co, n.inputs["Vector"])
    return n

def ramp(nt, fac, stops):
    r = nt.nodes.new("ShaderNodeValToRGB"); nt.links.new(fac, r.inputs["Fac"])
    els = r.color_ramp.elements
    for i, (p, c) in enumerate(stops):
        e = els[i] if i < 2 else els.new(p)
        e.position = p; e.color = (*c, 1)
    return r

def bump(nt, bsdf, h, strength, dist=0.02):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength; b.inputs["Distance"].default_value = dist
    nt.links.new(h, b.inputs["Height"]); nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])

# ---------- PBR procedural materials ----------
def mat_concrete(name, wet):
    m, nt, bsdf = node_mat(name); co = tex_coord(nt)
    n1 = noise(nt, 6, 12, 0.65, co); n2 = noise(nt, 60, 4, 0.5, co)
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "FLOAT"
    mix.inputs[0].default_value = 0.35
    nt.links.new(n1.outputs["Fac"], mix.inputs[2]); nt.links.new(n2.outputs["Fac"], mix.inputs[3])
    dark = 0.55 if wet else 1.0
    r = ramp(nt, mix.outputs[0], [(0.3, (0.36*dark, 0.355*dark, 0.34*dark)),
                                  (0.7, (0.62*dark, 0.61*dark, 0.58*dark))])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    rr = ramp(nt, n1.outputs["Fac"], [(0.3, (0.45 if wet else 0.8,)*3), (0.7, (0.75 if wet else 0.95,)*3)])
    nt.links.new(rr.outputs["Color"], bsdf.inputs["Roughness"])
    # pinholes + formwork seam lines
    vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.inputs["Scale"].default_value = 140
    nt.links.new(co, vor.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave"); wave.wave_profile = "SAW"
    wave.inputs["Scale"].default_value = 0.83; wave.inputs["Distortion"].default_value = 0.2
    wave.bands_direction = "Z"; nt.links.new(co, wave.inputs["Vector"])
    seam = ramp(nt, wave.outputs["Fac"], [(0.0, (0,)*3), (0.03, (1,)*3)])
    add = nt.nodes.new("ShaderNodeMath"); add.operation = "MULTIPLY"
    nt.links.new(vor.outputs["Distance"], add.inputs[0]); nt.links.new(seam.outputs["Color"], add.inputs[1])
    h = nt.nodes.new("ShaderNodeMath"); h.operation = "ADD"
    nt.links.new(add.outputs[0], h.inputs[0]); nt.links.new(n2.outputs["Fac"], h.inputs[1])
    bump(nt, bsdf, h.outputs[0], 0.35, 0.01)
    return m

def mat_soil():
    m, nt, bsdf = node_mat("DampSoil"); co = tex_coord(nt)
    n = noise(nt, 4, 14, 0.7, co); n2 = noise(nt, 35, 6, 0.6, co)
    r = ramp(nt, n.outputs["Fac"], [(0.35, (0.045, 0.03, 0.02)), (0.55, (0.10, 0.07, 0.045)),
                                     (0.75, (0.16, 0.115, 0.075))])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    bump(nt, bsdf, n2.outputs["Fac"], 0.8, 0.05)
    return m

def mat_gravel():
    m, nt, bsdf = node_mat("Gravel"); co = tex_coord(nt)
    v = nt.nodes.new("ShaderNodeTexVoronoi"); v.inputs["Scale"].default_value = 45
    nt.links.new(co, v.inputs["Vector"])
    r = ramp(nt, v.outputs["Color"], [(0.0, (0.18, 0.17, 0.16)), (0.5, (0.42, 0.40, 0.37)),
                                       (1.0, (0.58, 0.55, 0.50))])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    inv = ramp(nt, v.outputs["Distance"], [(0.0, (1,)*3), (0.6, (0,)*3)])
    bump(nt, bsdf, inv.outputs["Color"], 1.0, 0.03)
    return m

def mat_rust():
    m, nt, bsdf = node_mat("RustedRebar"); co = tex_coord(nt)
    n = noise(nt, 25, 10, 0.7, co)
    r = ramp(nt, n.outputs["Fac"], [(0.35, (0.12, 0.05, 0.02)), (0.55, (0.38, 0.14, 0.04)),
                                     (0.8, (0.25, 0.22, 0.2))])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    met = ramp(nt, n.outputs["Fac"], [(0.6, (0,)*3), (0.85, (0.8,)*3)])
    nt.links.new(met.outputs["Color"], bsdf.inputs["Metallic"])
    bsdf.inputs["Roughness"].default_value = 0.75
    bump(nt, bsdf, n.outputs["Fac"], 0.5, 0.004)
    return m

def mat_plywood():
    m, nt, bsdf = node_mat("WeatheredPlywood"); co = tex_coord(nt)
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1, 1, 12)
    nt.links.new(co, mp.inputs["Vector"])
    w = nt.nodes.new("ShaderNodeTexWave"); w.inputs["Scale"].default_value = 2.5
    w.inputs["Distortion"].default_value = 6; w.inputs["Detail"].default_value = 6
    nt.links.new(mp.outputs[0], w.inputs["Vector"])
    stain = noise(nt, 3, 6, 0.6, co)
    mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "FLOAT"; mx.inputs[0].default_value = 0.5
    nt.links.new(w.outputs["Fac"], mx.inputs[2]); nt.links.new(stain.outputs["Fac"], mx.inputs[3])
    r = ramp(nt, mx.outputs[0], [(0.25, (0.20, 0.14, 0.08)), (0.5, (0.45, 0.33, 0.2)),
                                  (0.75, (0.58, 0.47, 0.32))])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bump(nt, bsdf, w.outputs["Fac"], 0.15)
    return m

def mat_simple(name, col, rough, metal=0.0):
    m, nt, bsdf = node_mat(name)
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    bsdf.inputs["Roughness"].default_value = rough; bsdf.inputs["Metallic"].default_value = metal
    return m

CONC, WETC = mat_concrete("CuredConcrete", False), mat_concrete("FreshWetConcrete", True)
SOIL, GRAVEL, RUST, PLY = mat_soil(), mat_gravel(), mat_rust(), mat_plywood()
WETSOIL = mat_simple("WetRut", (0.03, 0.02, 0.012), 0.8)
STEEL = mat_simple("TieRodSteel", (0.3, 0.3, 0.32), 0.4, 1.0)
WATER = mat_simple("Puddle", (0.08, 0.07, 0.05), 0.03); WATER.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.6

# ---------- Poly Haven scanned PBR textures (override procedurals if present) ----------
import os
PH = os.environ.get("PH_DIR", "")
def ph_mat(name, aid, scale, dark=1.0, rough_mul=1.0, bump_s=0.6):
    m, nt, bsdf = node_mat(name); co = tex_coord(nt)
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (scale,) * 3
    nt.links.new(co, mp.inputs["Vector"])
    def img(k, color):
        f = [x for x in os.listdir(PH) if x.startswith(f"{aid}_{k}.")][0]
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(os.path.join(PH, f))
        t.projection = "BOX"; t.projection_blend = 0.25
        if not color: t.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs[0], t.inputs["Vector"]); return t
    d = img("diff", True)
    if dark != 1.0:
        mu = nt.nodes.new("ShaderNodeMix"); mu.data_type = "RGBA"; mu.blend_type = "MULTIPLY"
        mu.inputs[0].default_value = 1.0; mu.inputs[7].default_value = (dark, dark, dark * 0.97, 1)
        nt.links.new(d.outputs["Color"], mu.inputs[6]); nt.links.new(mu.outputs[2], bsdf.inputs["Base Color"])
    else:
        nt.links.new(d.outputs["Color"], bsdf.inputs["Base Color"])
    r = img("rough", False)
    rm = nt.nodes.new("ShaderNodeMath"); rm.operation = "MULTIPLY"; rm.inputs[1].default_value = rough_mul
    nt.links.new(r.outputs["Color"], rm.inputs[0]); nt.links.new(rm.outputs[0], bsdf.inputs["Roughness"])
    n = img("nor", False); nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    h = img("disp", False); b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = bump_s; b.inputs["Distance"].default_value = 0.03
    nt.links.new(h.outputs["Color"], b.inputs["Height"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return m

if PH:
    SOIL = ph_mat("SoilWall", "excavated_soil_wall", 0.6)
    MUD = ph_mat("SiteMud", "brown_mud_rocks_01", 0.35)
    MOUND = ph_mat("SpoilHeap", "rocky_trail", 0.5, bump_s=1.0)
    GRASS = ph_mat("Grass", "sparse_grass", 1.0)
    GRAVEL = ph_mat("Gravel", "gravel", 1.2, bump_s=1.0)
    PLY = ph_mat("Plywood", "plywood", 0.8)
    RUST = ph_mat("Rebar", "rusty_metal_02", 4.0)
    CONC = ph_mat("Concrete", "concrete", 0.7)
    WETC = ph_mat("WetConcrete", "concrete", 0.7, dark=0.55, rough_mul=0.55)
    WETSOIL = ph_mat("RutMud", "brown_mud_rocks_01", 0.35, dark=0.6, rough_mul=0.5)
else:
    MUD = MOUND = GRASS = SOIL

# ---------- 1. ground, trench, spoil mounds ----------
EXT = 80
for s in (-1, 1):
    w = EXT - TW / 2
    g = box(f"Ground_{s}", (w, L + 80, TD), (s * (TW / 2 + w / 2), L / 2, -TD / 2), SOIL)
    g.modifiers["bev"] if False else None
box("TrenchFloor", (TW + 0.02, L, 0.3), (0, L / 2, -TD - 0.15), SOIL)
# far end wall of trench (unexcavated)
box("TrenchEnd", (TW, 80, TD), (0, L + 40, -TD / 2), SOIL)

def mound(x, y, sx, sy, h):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, location=(x, y, 0))
    o = bpy.context.object; o.scale = (sx, sy, h)
    bpy.ops.object.transform_apply(scale=True)
    t = bpy.data.textures.new("clump", "CLOUDS"); t.noise_scale = 0.35
    d = o.modifiers.new("disp", "DISPLACE"); d.texture = t; d.strength = 0.25
    sub = o.modifiers.new("sub", "SUBSURF"); sub.levels = 2; sub.render_levels = 2
    o.modifiers.move(1, 0)
    o.data.materials.append(MOUND); bpy.ops.object.shade_smooth()

for y in (range(0, 11, 2) if STAGE not in (1, 8) else []):
    mound(-(TW / 2 + 1.1 + random.uniform(-.2, .2)), y + random.uniform(-.4, .4),
          random.uniform(0.9, 1.3), random.uniform(1.2, 1.7), random.uniform(0.35, 0.6))
    mound(TW / 2 + 1.3 + random.uniform(-.2, .2), y + 1 + random.uniform(-.4, .4),
          random.uniform(0.7, 1.0), random.uniform(1.0, 1.4), random.uniform(0.25, 0.45))

# surface layers: muddy work strip near trench, grass beyond
for sx in (-1, 1):
    box("MudStrip", (6.5, L + 80, 0.03), (sx * (TW / 2 + 3.25), L / 2, 0.0), MUD)
    box("GrassField", (70, L + 80, 0.03), (sx * (TW / 2 + 6.5 + 35), L / 2, -0.005), GRASS)
box("MudEnd", (TW + 0.1, 80, 0.03), (0, L + 40.05, 0.0), MUD)
# safety cones + caution tape on left edge
CONE = mat_simple("ConeOrange", (0.9, 0.18, 0.02), 0.45); WHITE = mat_simple("Reflective", (0.85, 0.85, 0.85), 0.3)
TAPE = mat_simple("CautionTape", (0.95, 0.75, 0.02), 0.5)
cones = []
for y in (-0.6, 2.4, 5.4, 8.4):
    x = -(TW / 2 + 0.22)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.15, radius2=0.025, depth=0.7, location=(x, y, 0.38))
    bpy.context.object.data.materials.append(CONE); bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.105, depth=0.08, location=(x, y, 0.45))
    bpy.context.object.data.materials.append(WHITE)
    box("ConeBase", (0.36, 0.36, 0.03), (x, y, 0.03), CONE)
    cones.append(y)
for a, b in zip(cones, cones[1:]):
    t = box("Tape", (0.005, b - a, 0.07), (-(TW / 2 + 0.22), (a + b) / 2, 0.62), TAPE)
# tire ruts on right bank
for dx in (2.6, 4.4):
    box("Rut", (0.4, L + 30, 0.04), (dx + 1.5, L / 2, -0.012), WETSOIL)

if STAGE == 1:   # unexcavated ground, pegs + string line
    box("Fill", (TW, L, TD), (0, L / 2, -TD / 2), SOIL); box("FillTop", (TW + 0.1, L, 0.03), (0, L / 2, 0.0), MUD)
    PEG = mat_simple("Peg", (0.45, 0.3, 0.15), 0.8); STR = mat_simple("String", (1.0, 0.25, 0.0), 0.5)
    for x in (-TW / 2, TW / 2):
        for y in range(0, 11, 2): box("Peg", (0.05, 0.05, 0.5), (x, y, 0.22), PEG)
        box("String", (0.006, L, 0.006), (x, L / 2, 0.4), STR)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=1.6, location=(1.9, 1.5, 0.8)); bpy.context.object.data.materials.append(STEEL)
    box("Staff", (0.05, 0.03, 2.0), (-1.6, 7.0, 1.0), mat_simple("Staff", (0.9, 0.85, 0.2), 0.5))
if STAGE == 8:  # backfill between drain and trench sides
    for sx in (-1, 1):
        box("Backfill", ((TW - OUTW) / 2, L, -Z0), (sx * (OUTW / 2 + (TW - OUTW) / 4), L / 2, Z0 / 2), MUD)
# ---------- 2. gravel sub-base ----------
if STAGE == 0 or STAGE >= 3: box("GravelSubBase", (TW, L, GRAV), (0, L / 2, -TD + GRAV / 2), GRAVEL)
if STAGE in (0, 3): bpy.ops.mesh.primitive_plane_add(size=1, location=(0.25, 8.4, -TD + GRAV + 0.004))
if STAGE in (0, 3): p = bpy.context.object; p.scale = (0.9, 1.3, 1); p.data.materials.append(WATER)

# ---------- 3. U-channel (cured section + fresh section) ----------
def channel(y0, y1, mat, tag):
    ln = y1 - y0; yc = (y0 + y1) / 2; h = TOP - (Z0 + BASE)
    parts = [box(f"Base_{tag}", (OUTW, ln, BASE), (0, yc, Z0 + BASE / 2), mat, 0.01)]
    for s in (-1, 1):
        parts.append(box(f"Wall_{tag}{s}", (WALL, ln, h), (s * (OUTW / 2 - WALL / 2), yc, Z0 + BASE + h / 2), mat, 0.012))
    return parts

if STAGE == 0: channel(0, 4.0, CONC, "cured"); channel(4.0, CAST_END, WETC, "fresh")
if STAGE == 6: channel(0, CAST_END, WETC, "fresh")
if STAGE == 7:
    channel(0, L, WETC, "fresh"); HESS = ph_mat("Hessian", "plywood", 2.0, dark=0.45) if PH else WETC
    for sx in (-1, 1): box("Hessian", (WALL + 0.06, L, 0.015), (sx * (OUTW / 2 - WALL / 2), L / 2, TOP + 0.008), HESS)
    box("HessianBase", (OUTW - 2 * WALL, L, 0.012), (0, L / 2, Z0 + BASE + 0.006), HESS)
if STAGE == 8:
    channel(0, L, CONC, "cured")
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, L / 2, Z0 + BASE + 0.12)); w_ = bpy.context.object
    w_.scale = (OUTW - 2 * WALL - 0.01, L, 1); w_.data.materials.append(mat_simple("DrainWater", (0.12, 0.11, 0.08), 0.02))
RB0, LK0 = {0: (CAST_END - 0.3, CAST_END + 0.15), 4: (0, 0.15), 5: (0, 0.15), 6: (CAST_END - 0.3, CAST_END + 0.15)}.get(STAGE, (None, None))
RB1 = BAR_END if STAGE == 0 else L
FW0, FW1 = {0: (4.0, CAST_END), 5: (0.0, L), 6: (0.0, CAST_END)}.get(STAGE, (None, None))

# ---------- rebar starters at the unfinished end ----------
if RB0 is not None:
 bars = []; R = 0.006; cov = 0.05
 xs_wall = [-(OUTW / 2 - cov - 0.02), -(OUTW / 2 - WALL + cov + 0.02)]
 xs_wall += [-x for x in xs_wall]
 zb = [Z0 + cov, Z0 + BASE - cov]
 for x in xs_wall:                                    # longitudinal wall bars
     for z in [Z0 + BASE + 0.15 + i * 0.25 for i in range(5)]:
         bar((x, RB0, z), (x, RB1, z), R, RUST, bars)
 for z in zb:                                          # longitudinal base bars
     for x in [-0.65 + i * 0.2 for i in range(8)]:
         bar((x, RB0, z), (x, RB1, z), R, RUST, bars)
 y = LK0
 while y < RB1:                                    # U-shaped links
     for xo, xi in ((xs_wall[0], xs_wall[1]), (xs_wall[2], xs_wall[3])):
         for x in (xo, xi):
             bar((x, y, zb[0] if x in (xs_wall[0], xs_wall[2]) else zb[1]), (x, y, TOP - 0.03), R * 1.3, RUST, bars)
     for z in zb:
         bar((xs_wall[0], y, z), (xs_wall[2], y, z), R * 1.3, RUST, bars)
     y += 0.2
 join(bars, "RebarCage")

# ---------- modular formwork with tie-rods over the active pour ----------
if FW0 is not None:
 fw = []; PW, PT = 0.6, 0.018
 for s in (-1, 1):
     for face, off in (("out", OUTW / 2 + PT / 2), ("in", OUTW / 2 - WALL - PT / 2)):
         y = FW0
         while y < FW1 - 0.01:
             fw.append(box("Ply", (PT, PW - 0.008, TOP - (Z0 + BASE) + 0.12),
                           (s * off, y + PW / 2, (TOP + Z0 + BASE) / 2 + 0.06), PLY))
             y += PW
     for y in [FW0 + PW * i for i in range(1, int((FW1 - FW0) / PW))]:     # soldiers / walers
         fw.append(box("Waler", (0.07, 0.07, TOP - (Z0 + BASE)), (s * (OUTW / 2 + 0.055), y, (TOP + Z0 + BASE) / 2), PLY))
 for y in [FW0 + PW * i for i in range(1, int((FW1 - FW0) / PW))]:         # tie-rods through both walls
     for z in (Z0 + BASE + 0.25, TOP - 0.25):
         bar((-(OUTW / 2 + 0.12), y, z), (OUTW / 2 + 0.12, y, z), 0.008, STEEL, fw)
         for s in (-1, 1):
             bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.03, depth=0.03,
                                                 location=(s * (OUTW / 2 + 0.1), y, z), rotation=(0, math.pi / 2, 0))
             bpy.context.object.data.materials.append(STEEL); fw.append(bpy.context.object)
 for y in (FW0 + 0.3, FW1 - 0.5):                                  # spreader struts inside channel
     fw.append(box("Strut", (OUTW - 2 * WALL - 2 * PT, 0.06, 0.06), (0, y, TOP - 0.1), PLY))
 join(fw, "Formwork")

# stacked precast cover slabs on right bank
for i in (range(5) if STAGE not in (1, 2) else []):
    box(f"Cover{i}", (1.8, 0.6, 0.1), (3.4, 0.2 + random.uniform(-.03, .03), 0.05 + i * 0.105), CONC, 0.008).rotation_euler.z = random.uniform(-.03, .03)

# ---------- 5. world: Nishita sky, late afternoon ----------
w = bpy.data.worlds.new("Sky"); sc.world = w; w.use_nodes = True
sky = w.node_tree.nodes.new("ShaderNodeTexSky"); sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(14); sky.sun_rotation = math.radians(-60)
sky.air_density = 1.2; sky.dust_density = 3.0; sky.sun_intensity = 0.5
w.node_tree.links.new(sky.outputs["Color"], w.node_tree.nodes["Background"].inputs["Color"])
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

# ---------- camera: 35mm, 3/4 elevated ----------
bpy.ops.object.empty_add(location=(0, 5.2, -0.9)); tgt = bpy.context.object
bpy.ops.object.camera_add(location=(2.7, -2.6, 2.1)); cam = bpy.context.object
cam.data.lens = 35; cam.data.sensor_width = 36
c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
sc.camera = cam

# ---------- Cycles ----------
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"
sc.cycles.samples = int(sys.argv[sys.argv.index("--") + 2]) if "--" in sys.argv and len(sys.argv) > sys.argv.index("--") + 2 else 128
sc.cycles.use_denoising = True; sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.max_bounces = 6
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.filepath = OUT
bpy.ops.wm.save_as_mainfile(filepath=OUT.rsplit(".", 1)[0] + ".blend")
bpy.ops.render.render(write_still=True)
